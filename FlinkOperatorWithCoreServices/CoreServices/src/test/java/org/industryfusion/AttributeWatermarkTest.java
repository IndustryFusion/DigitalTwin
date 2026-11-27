/*
 * Copyright (c) 2026 IndustryFusion Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.industryfusion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.api.java.typeutils.RowTypeInfo;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.table.api.DataTypes;
import org.apache.flink.table.api.Schema;
import org.apache.flink.table.api.Table;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;
import org.apache.flink.types.Row;
import org.apache.flink.util.CloseableIterator;
import org.junit.jupiter.api.Test;

/**
 * The watermarks of the windowed tables in table_definition.sql (#1060).
 *
 * Both tables are aggregated in tumbling windows of one millisecond over the
 * record timestamp, and the records of one batch share a millisecond on
 * purpose (a value and its delete, the attributes of one entity). With
 * {@code WATERMARK FOR ts AS ts} a row whose ts equals the highest one seen is
 * late: once a watermark falls between two records of one millisecond, their
 * window fires with the first one only and the second is dropped. These tests
 * force that: an auto-watermark interval of 0 emits a watermark after every
 * record, which is the worst a loaded job can do.
 */
public class AttributeWatermarkTest {

    private static final String TUMBLE =
        "SELECT id, COUNT(*) AS n, LISTAGG(v) AS vs FROM TABLE(TUMBLE(TABLE t, DESCRIPTOR(ts), "
        + "INTERVAL '0.001' SECOND)) GROUP BY window_start, window_end, id";

    /** The WATERMARK expression of each table of table_definition.sql, by table name. */
    static Map<String, String> watermarks() throws IOException {
        String ddl;
        try (InputStream in = AttributeWatermarkTest.class.getResourceAsStream("/table_definition.sql")) {
            ddl = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
        Map<String, String> found = new HashMap<>();
        Matcher table = Pattern.compile("CREATE TABLE `?(\\w+)`?\\s*\\((.*?)\\)\\s*WITH", Pattern.DOTALL).matcher(ddl);
        while (table.find()) {
            Matcher wm = Pattern.compile("WATERMARK FOR ts AS ([^,\\n]+?)\\s*(?:,|\\n)").matcher(table.group(2));
            if (wm.find()) {
                found.put(table.group(1), wm.group(1).trim());
            }
        }
        return found;
    }

    /** id -> the values of its records in the window of the given millisecond, as the window aggregation counts them. */
    static Map<String, String> windowed(String watermark, List<Row> rows) throws Exception {
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(1);
        env.getConfig().setAutoWatermarkInterval(0);
        StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);
        DataStream<Row> stream = env.fromCollection(rows, new RowTypeInfo(
            new org.apache.flink.api.common.typeinfo.TypeInformation<?>[] {Types.STRING, Types.STRING, Types.LOCAL_DATE_TIME},
            new String[] {"id", "v", "ts"}));
        Table t = tEnv.fromDataStream(stream, Schema.newBuilder()
            .column("id", DataTypes.STRING())
            .column("v", DataTypes.STRING())
            .column("ts", DataTypes.TIMESTAMP(3))
            .watermark("ts", watermark)
            .build());
        tEnv.createTemporaryView("t", t);
        Map<String, String> out = new HashMap<>();
        try (CloseableIterator<Row> it = tEnv.executeSql(TUMBLE).collect()) {
            while (it.hasNext()) {
                Row r = it.next();
                out.merge((String) r.getField(0), (String) r.getField(2), (a, b) -> a + "|" + b);
            }
        }
        return out;
    }

    /** Two records of one millisecond, then a marker of a later one that closes their window. */
    static List<Row> batch() {
        LocalDateTime t = LocalDateTime.of(2026, 11, 27, 9, 3, 59, 557_000_000);
        List<Row> rows = new ArrayList<>();
        rows.add(Row.of("state", "ON", t));
        rows.add(Row.of("state", "OFF", t));
        rows.add(Row.of("temperature", "21", t));
        rows.add(Row.of("flush", "flush", t.plusNanos(27_000_000)));
        return rows;
    }

    @Test
    public void theWindowedTablesHaveAWatermark() throws IOException {
        Map<String, String> wm = watermarks();
        assertTrue(wm.containsKey("attributes"), "attributes: " + wm);
        assertTrue(wm.containsKey("attributes_insert"), "attributes_insert: " + wm);
    }

    @Test
    public void everyRecordOfOneMillisecondIsInItsWindow() throws Exception {
        for (Map.Entry<String, String> wm : watermarks().entrySet()) {
            Map<String, String> windows = windowed(wm.getValue(), batch());
            assertEquals("ON|OFF", sorted(windows.get("state")),
                wm.getKey() + " with WATERMARK FOR ts AS " + wm.getValue() + " dropped a record: " + windows);
            assertEquals("21", windows.get("temperature"), wm.getKey() + ": " + windows);
            assertEquals("flush", windows.get("flush"), wm.getKey() + ": " + windows);
        }
    }

    /** What the strictly ascending watermark did: shows that the test reproduces #1060. */
    @Test
    public void aWatermarkOfTheHighestTimestampDropsTheSecondRecordOfAMillisecond() throws Exception {
        Map<String, String> windows = windowed("ts", batch());
        assertEquals("ON", windows.get("state"), windows.toString());
        assertEquals(null, windows.get("temperature"), windows.toString());
    }

    private static String sorted(String vs) {
        if (vs == null) {
            return null;
        }
        String[] parts = vs.split("[|,]");
        java.util.Arrays.sort(parts, java.util.Comparator.reverseOrder());
        return String.join("|", parts);
    }
}

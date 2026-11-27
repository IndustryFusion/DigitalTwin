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
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.flink.api.common.eventtime.Watermark;
import org.apache.flink.api.common.eventtime.WatermarkOutput;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.api.java.typeutils.RowTypeInfo;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.table.api.DataTypes;
import org.apache.flink.table.api.Schema;
import org.apache.flink.table.api.bridge.java.StreamStatementSet;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;
import org.apache.flink.table.catalog.ResolvedSchema;
import org.apache.flink.table.connector.ChangelogMode;
import org.apache.flink.types.Row;
import org.apache.flink.types.RowKind;
import org.apache.flink.util.CloseableIterator;
import org.junit.jupiter.api.Test;

/**
 * The watermark of the tables Core Services aggregates in windows of one
 * millisecond (#1060).
 *
 * <p>The records of one batch share a millisecond on purpose (a value and its
 * delete, the attributes of one entity). A watermark equal to the highest
 * timestamp seen makes the next record of that millisecond late: its window
 * fires with the first record and drops the others. The window tests force
 * that: the generator emits after every record, which is the worst a loaded
 * job can do. The generator tests drive the quiet period with a manual clock.
 */
public class AttributeWatermarkTest {

    private static final long T = 1_000_000L;
    private static final long IDLE = 1000L;
    private static final long NEVER_QUIET = 3_600_000L;

    /** A clock the test sets. */
    static final class ManualClock implements IdleCatchUpWatermarks.Clock {
        private static final long serialVersionUID = 1L;
        private long now;

        @Override
        public long millis() {
            return now;
        }
    }

    /** The watermarks a generator emitted. */
    static final class Emitted implements WatermarkOutput {
        private final List<Long> watermarks = new ArrayList<>();

        @Override
        public void emitWatermark(final Watermark watermark) {
            watermarks.add(watermark.getTimestamp());
        }

        @Override
        public void markIdle() {
        }

        @Override
        public void markActive() {
        }

        Long last() {
            return watermarks.isEmpty() ? null : watermarks.get(watermarks.size() - 1);
        }
    }

    // --- the generator ---------------------------------------------------

    @Test
    public void whileRecordsArriveTheWatermarkStaysOneMillisecondBehind() {
        ManualClock clock = new ManualClock();
        Emitted out = new Emitted();
        IdleCatchUpWatermarks.Generator gen = new IdleCatchUpWatermarks.Generator(IDLE, 1, clock, false);
        gen.onPeriodicEmit(out);
        assertEquals(null, out.last(), "no watermark before the first record");
        gen.onEvent(Row.of(), T, out);
        clock.now = IDLE - 1;
        gen.onPeriodicEmit(out);
        assertEquals(T - 1, out.last(), "a record of millisecond T may still come: its window stays open");
    }

    @Test
    public void afterAQuietPeriodTheWatermarkCatchesUpAndClosesTheLastWindow() {
        ManualClock clock = new ManualClock();
        Emitted out = new Emitted();
        IdleCatchUpWatermarks.Generator gen = new IdleCatchUpWatermarks.Generator(IDLE, 1, clock, false);
        gen.onEvent(Row.of(), T, out);
        gen.onEvent(Row.of(), T, out);
        clock.now = IDLE;
        gen.onPeriodicEmit(out);
        // A 1 ms window [T, T+1) fires at watermark T.
        assertEquals(T, out.last(), "the window of T closes without a later record");
    }

    @Test
    public void aNewRecordEndsTheQuietPeriod() {
        ManualClock clock = new ManualClock();
        Emitted out = new Emitted();
        IdleCatchUpWatermarks.Generator gen = new IdleCatchUpWatermarks.Generator(IDLE, 1, clock, false);
        gen.onEvent(Row.of(), T, out);
        clock.now = IDLE;
        gen.onPeriodicEmit(out);
        clock.now = IDLE + 10;
        gen.onEvent(Row.of(), T + 5, out);
        clock.now = IDLE + 20;
        gen.onPeriodicEmit(out);
        assertEquals(T + 4, out.last(), "the window of T+5 stays open again");
        clock.now = 2 * IDLE + 10;
        gen.onPeriodicEmit(out);
        assertEquals(T + 5, out.last());
    }

    @Test
    public void aBacklogOfOldRecordsNeverCatchesUp() {
        ManualClock clock = new ManualClock();
        Emitted out = new Emitted();
        IdleCatchUpWatermarks.Generator gen = new IdleCatchUpWatermarks.Generator(IDLE, 1, clock, false);
        // replayed: written long before it is processed
        clock.now = T + 10 * IDLE;
        gen.onEvent(Row.of(), T, out);
        clock.now += 5 * IDLE;
        gen.onPeriodicEmit(out);
        assertEquals(T - 1, out.last(), "the rest of millisecond T may still wait in a buffer");
    }

    @Test
    public void aLiveRecordCatchesUpOnlyWhileItIsFresh() {
        ManualClock clock = new ManualClock();
        Emitted out = new Emitted();
        IdleCatchUpWatermarks.Generator gen = new IdleCatchUpWatermarks.Generator(IDLE, 1, clock, false);
        clock.now = T + 5;
        gen.onEvent(Row.of(), T, out);
        clock.now = T + 5 + IDLE;
        gen.onPeriodicEmit(out);
        assertEquals(T, out.last(), "written and processed live: the window closes after the quiet period");
    }

    @Test
    public void theWatermarkNeverGoesBack() {
        ManualClock clock = new ManualClock();
        Emitted out = new Emitted();
        IdleCatchUpWatermarks.Generator gen = new IdleCatchUpWatermarks.Generator(IDLE, 1, clock, false);
        gen.onEvent(Row.of(), T, out);
        clock.now = IDLE;
        gen.onPeriodicEmit(out);
        gen.onEvent(Row.of(), T - 50, out);
        gen.onPeriodicEmit(out);
        for (int i = 1; i < out.watermarks.size(); i++) {
            assertTrue(out.watermarks.get(i) > out.watermarks.get(i - 1), out.watermarks.toString());
        }
        assertEquals(T, out.last());
    }

    // --- table_definition.sql and the job ----------------------------------

    @Test
    public void theWindowedSourcesDeclareNoWatermarkOfTheirOwn() throws Exception {
        String ddl = CoreServices.loadResourceFile("table_definition.sql");
        for (String source : CoreServices.WINDOWED_SOURCES.keySet()) {
            Matcher table = Pattern.compile("CREATE TABLE `?" + source + "`?\\s*\\((.*?)\\)\\s*WITH", Pattern.DOTALL)
                .matcher(ddl);
            assertTrue(table.find(), source + " is defined");
            assertFalse(table.group(1).matches("(?s).*^\\s*WATERMARK.*"), source + " declares a WATERMARK");
        }
    }

    @Test
    public void theJobPlansWithTheWatermarkedViews() {
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);
        for (String def : CoreServices.loadResourceFile("table_definition.sql").split(";")) {
            if (!def.trim().isEmpty()) {
                tEnv.executeSql(def + ';');
                CoreServices.registerWatermarkedViews(tEnv, IDLE);
            }
        }
        for (String view : new String[] {"attributes", "attributes_insert"}) {
            ResolvedSchema schema = tEnv.from(view).getResolvedSchema();
            ResolvedSchema source = tEnv.from(view + CoreServices.SOURCE_SUFFIX).getResolvedSchema();
            assertEquals(1, schema.getWatermarkSpecs().size(), view + ": " + schema);
            assertEquals("ts", schema.getWatermarkSpecs().get(0).getRowtimeAttribute(), view + ": " + schema);
            // The same columns, types and key as the table the statements read before.
            assertEquals(source.getColumnNames(), schema.getColumnNames(), view);
            for (String column : source.getColumnNames()) {
                assertEquals(source.getColumn(column).get().getDataType().getLogicalType().copy(true),
                    schema.getColumn(column).get().getDataType().getLogicalType().copy(true), view + "." + column);
            }
            assertEquals(source.getPrimaryKey().map(k -> k.getColumns()),
                schema.getPrimaryKey().map(k -> k.getColumns()), view + " key");
        }
        assertEquals(java.util.Optional.of(java.util.Arrays.asList("id", "datasetId")),
            tEnv.from("attributes_insert").getResolvedSchema().getPrimaryKey().map(k -> k.getColumns()));
        StreamStatementSet set = tEnv.createStatementSet();
        for (String stmt : CoreServices.loadResourceFile("sql_statements.sql").split(";")) {
            if (stmt.trim().toUpperCase().startsWith("INSERT")) {
                set.addInsertSql(stmt.trim());
            }
        }
        String plan = set.explain();
        assertTrue(plan.contains("WindowAggregate") && plan.contains("GroupWindowAggregate"), plan);
    }

    // --- the windows ---------------------------------------------------------

    private static final String TUMBLE =
        "SELECT id, LISTAGG(v) AS vs FROM TABLE(TUMBLE(TABLE t, DESCRIPTOR(ts), "
        + "INTERVAL '0.001' SECOND)) GROUP BY window_start, window_end, id";

    private static final String WRITEBACK =
        "SELECT id, LAST_VALUE(v) AS v FROM t GROUP BY id, TUMBLE(ts, INTERVAL '0.001' SECOND)";

    /** Two records of one millisecond, then a marker of a later one that closes their window. */
    static List<Row> batch(final boolean changelog) {
        LocalDateTime t = LocalDateTime.of(2026, 11, 27, 9, 3, 59, 557_000_000);
        List<Row> rows = new ArrayList<>();
        rows.add(row(changelog, "state", "ON", t));
        rows.add(row(changelog, "state", "OFF", t));
        rows.add(row(changelog, "temperature", "21", t));
        rows.add(row(changelog, "flush", "flush", t.plusNanos(27_000_000)));
        return rows;
    }

    private static Row row(final boolean changelog, final String id, final String v, final LocalDateTime ts) {
        return changelog ? Row.ofKind(RowKind.INSERT, id, v, ts) : Row.of(id, v, ts);
    }

    /** id -> the values the query emitted for it, with a watermark lag of {@code lag} after every record. */
    static Map<String, String> windowed(final String query, final boolean changelog, final long lag) throws Exception {
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(1);
        StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);
        DataStream<Row> stream = env.fromCollection(batch(changelog), new RowTypeInfo(
            new TypeInformation<?>[] {Types.STRING, Types.STRING, Types.LOCAL_DATE_TIME},
            new String[] {"id", "v", "ts"}));
        Schema schema = Schema.newBuilder()
            .column("id", DataTypes.STRING())
            .column("v", DataTypes.STRING())
            .column("ts", DataTypes.TIMESTAMP(3))
            .build();
        tEnv.createTemporaryView("t_source", changelog
            ? tEnv.fromChangelogStream(stream, schema) : tEnv.fromDataStream(stream, schema));
        IdleCatchUpWatermarks.register(tEnv, "t_source", "t",
            changelog ? ChangelogMode.all() : ChangelogMode.insertOnly(),
            IdleCatchUpWatermarks.strategy(NEVER_QUIET, lag, System::currentTimeMillis, true));
        Map<String, String> out = new HashMap<>();
        try (CloseableIterator<Row> it = tEnv.executeSql(query).collect()) {
            while (it.hasNext()) {
                Row r = it.next();
                if (r.getKind() == RowKind.INSERT || r.getKind() == RowKind.UPDATE_AFTER) {
                    out.put((String) r.getField(0), (String) r.getField(1));
                }
            }
        }
        return out;
    }

    @Test
    public void everyRecordOfOneMillisecondIsInItsWindow() throws Exception {
        Map<String, String> windows = windowed(TUMBLE, false, IdleCatchUpWatermarks.LAG_MILLIS);
        assertEquals("ON,OFF", windows.get("state"), "a record was dropped: " + windows);
        assertEquals("21", windows.get("temperature"), windows.toString());
        assertEquals("flush", windows.get("flush"), windows.toString());
    }

    @Test
    public void theWritebackKeepsTheLastRecordOfAMillisecond() throws Exception {
        Map<String, String> windows = windowed(WRITEBACK, true, IdleCatchUpWatermarks.LAG_MILLIS);
        assertEquals("OFF", windows.get("state"), "the later record was dropped: " + windows);
        assertEquals("21", windows.get("temperature"), windows.toString());
    }

    /** What `WATERMARK FOR ts AS ts` did: shows that the window tests reproduce #1060. */
    @Test
    public void aWatermarkOfTheHighestTimestampDropsTheSecondRecordOfAMillisecond() throws Exception {
        Map<String, String> windows = windowed(TUMBLE, false, 0);
        assertEquals("ON", windows.get("state"), windows.toString());
        assertEquals(null, windows.get("temperature"), windows.toString());
        Map<String, String> writeback = windowed(WRITEBACK, true, 0);
        assertEquals("ON", writeback.get("state"), writeback.toString());
    }
}

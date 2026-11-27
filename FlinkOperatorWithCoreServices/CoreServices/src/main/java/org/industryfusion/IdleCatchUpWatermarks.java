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

import java.io.Serializable;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

import org.apache.flink.api.common.eventtime.Watermark;
import org.apache.flink.api.common.eventtime.WatermarkGenerator;
import org.apache.flink.api.common.eventtime.WatermarkOutput;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.table.api.Schema;
import org.apache.flink.table.api.Table;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;
import org.apache.flink.table.catalog.Column;
import org.apache.flink.table.connector.ChangelogMode;
import org.apache.flink.types.Row;

/**
 * The watermark of the tables Core Services aggregates in windows of one
 * millisecond (#1060).
 *
 * <p>The records of one batch share a millisecond on purpose: the attributes of
 * one entity, a value and its delete. A watermark equal to the highest
 * timestamp seen makes the next record of that millisecond late, so its window
 * fires with the first record and drops the others. While records arrive, the
 * watermark therefore stays one millisecond behind the highest timestamp, and a
 * window closes once a later millisecond arrives. After {@code idleMillis}
 * without a record it catches up to the highest timestamp, so the last window
 * before a quiet period closes too instead of waiting for the next record.
 *
 * <p>The quiet period is measured from the last record PROCESSED. So it catches
 * up only while the newest record is fresh, written less than two quiet periods
 * ago: a backlog (the replay at every start) never closes a window early. What
 * remains: a record of a millisecond processed more than the quiet period after
 * another record of it is late. That needs a live stall of the job of one to
 * two quiet periods inside one batch, whose records are written within
 * milliseconds and usually fetched together.
 *
 * <p>Flink SQL has no such strategy, so the source tables are declared without
 * a watermark, and the tables the statements read are views over a DataStream
 * that carries this one.
 */
public final class IdleCatchUpWatermarks {

    /** The rowtime column of the watermarked tables. */
    public static final String ROWTIME = "ts";

    /** The lag behind the highest timestamp while records arrive. */
    public static final long LAG_MILLIS = 1;

    /** A wall clock, replaceable in tests. */
    public interface Clock extends Serializable {
        /** @return the current time in milliseconds */
        long millis();
    }

    private IdleCatchUpWatermarks() {
    }

    /** One millisecond behind the highest timestamp, the highest one after a quiet period. */
    public static final class Generator implements WatermarkGenerator<Row> {
        private final long idleMillis;
        private final long lagMillis;
        private final Clock clock;
        private final boolean emitOnEvent;
        private long maxTimestamp = Long.MIN_VALUE;
        private long lastEventAt;
        private long emitted = Long.MIN_VALUE;

        public Generator(final long idleMillis, final long lagMillis, final Clock clock, final boolean emitOnEvent) {
            this.idleMillis = idleMillis;
            this.lagMillis = lagMillis;
            this.clock = clock;
            this.emitOnEvent = emitOnEvent;
        }

        @Override
        public void onEvent(final Row event, final long eventTimestamp, final WatermarkOutput output) {
            if (eventTimestamp > maxTimestamp) {
                maxTimestamp = eventTimestamp;
            }
            lastEventAt = clock.millis();
            if (emitOnEvent && maxTimestamp != Long.MIN_VALUE) {
                emit(output, maxTimestamp - lagMillis);
            }
        }

        @Override
        public void onPeriodicEmit(final WatermarkOutput output) {
            if (maxTimestamp == Long.MIN_VALUE) {
                return;
            }
            final long now = clock.millis();
            final boolean quiet = now - lastEventAt >= idleMillis;
            // The timestamp is the write time of the record. A newest record
            // much older than the quiet period was read from a backlog (the
            // replay at every start, a stalled job), where the rest of its
            // millisecond may still wait in a buffer: no catch-up then, its
            // window waits for a later record as without the catch-up.
            final boolean fresh = now - maxTimestamp < 2 * idleMillis;
            emit(output, quiet && fresh ? maxTimestamp : maxTimestamp - lagMillis);
        }

        private void emit(final WatermarkOutput output, final long watermark) {
            if (watermark > emitted) {
                emitted = watermark;
                output.emitWatermark(new Watermark(watermark));
            }
        }
    }

    /**
     * The strategy: timestamps from the {@value #ROWTIME} column.
     *
     * @param idleMillis  quiet time after which the watermark catches up
     * @param lagMillis   lag behind the highest timestamp while records arrive
     * @param clock       the wall clock
     * @param emitOnEvent also emit after every record (tests: the worst a loaded job does)
     * @return the strategy
     */
    public static WatermarkStrategy<Row> strategy(final long idleMillis, final long lagMillis, final Clock clock,
            final boolean emitOnEvent) {
        return WatermarkStrategy.<Row>forGenerator(ctx -> new Generator(idleMillis, lagMillis, clock, emitOnEvent))
            .withTimestampAssigner((row, previous) -> timestamp(row, previous));
    }

    /** The production strategy. */
    public static WatermarkStrategy<Row> strategy(final long idleMillis) {
        return strategy(idleMillis, LAG_MILLIS, System::currentTimeMillis, false);
    }

    private static long timestamp(final Row row, final long previous) {
        final Object value = row.getField(ROWTIME);
        // TIMESTAMP(3) is a wall time without zone; Flink compares it with
        // watermarks as if it were UTC.
        return value instanceof LocalDateTime ? ((LocalDateTime) value).toInstant(ZoneOffset.UTC).toEpochMilli() : previous;
    }

    /**
     * Registers {@code view} as {@code source} with the {@value #ROWTIME}
     * column as rowtime and the given watermark.
     *
     * @param tableEnv the table environment
     * @param source   a table without a watermark
     * @param view     the name the statements read
     * @param mode     the changes the source emits: insert-only for an append
     *                 topic (the window TVFs need it), all for an upsert topic
     * @param strategy the watermark strategy
     */
    public static void register(final StreamTableEnvironment tableEnv, final String source, final String view,
            final ChangelogMode mode, final WatermarkStrategy<Row> strategy) {
        final Table table = tableEnv.from(source);
        final DataStream<Row> rows = tableEnv.toChangelogStream(table)
                .assignTimestampsAndWatermarks(strategy)
                .name(view + " watermarks");
        final Schema.Builder schema = Schema.newBuilder();
        for (final Column column : table.getResolvedSchema().getColumns()) {
            schema.column(column.getName(), column.getDataType());
        }
        // The key of an upsert source, so the planner knows it as before.
        table.getResolvedSchema().getPrimaryKey()
            .ifPresent(key -> schema.primaryKeyNamed(key.getName(), key.getColumns()));
        schema.watermark(ROWTIME, "SOURCE_WATERMARK()");
        tableEnv.createTemporaryView(view, tableEnv.fromChangelogStream(rows, schema.build(), mode));
    }
}

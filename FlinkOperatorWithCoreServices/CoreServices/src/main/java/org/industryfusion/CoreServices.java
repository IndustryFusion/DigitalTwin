package org.industryfusion;

import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.connector.kafka.sink.KafkaSink;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.bridge.java.StreamStatementSet;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;
import org.apache.flink.streaming.api.windowing.assigners.EventTimeSessionWindows;
import org.apache.flink.table.connector.ChangelogMode;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;
import java.time.Duration;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

//String alertsTopic = "iff.alerts";
public class CoreServices {
    private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger(CoreServices.class);

    /**
     * The source tables of table_definition.sql that the statements aggregate
     * in 1 ms windows, and the changes each emits. Each is read through a view
     * named without the suffix, which carries the watermark (#1060).
     */
    public static final Map<String, ChangelogMode> WINDOWED_SOURCES = new LinkedHashMap<>();

    static {
        // An append topic: the window TVF of ngsild_updates needs insert-only input.
        WINDOWED_SOURCES.put("attributes_source", ChangelogMode.insertOnly());
        // An upsert topic, read by the writeback's group window.
        WINDOWED_SOURCES.put("attributes_insert_source", ChangelogMode.all());
    }

    /** The suffix of a watermarked source table. */
    public static final String SOURCE_SUFFIX = "_source";

    /** Quiet time after which the watermark catches up with the last record, by default. */
    public static final String DEFAULT_IDLE_MS = "1000";

    public static void main(final String[] args) throws Exception {
        String alertsBulkTopic = System.getenv("ALERTS_BULK_TOPIC");
        if (alertsBulkTopic == null) {
            alertsBulkTopic = "iff.alerts.bulk"; // Default value if environment variable is not set
        }
        String kafkaBootstrap = System.getenv("KAFKA_BOOTSTRAP");
        if (kafkaBootstrap == null) {
            kafkaBootstrap = "my-cluster-kafka-bootstrap:9092"; // Default value if environment variable is not set
        }
        LOG.info("kafkaBootstrap is: {}", kafkaBootstrap);
        LOG.info("alertsBulkTopic is: {}", alertsBulkTopic);
        String alertsTopic = System.getenv("ALERTS_TOPIC");
        if (alertsTopic == null) {
            alertsTopic = "iff.alerts"; // Default value if environment variable is not set
        }
        LOG.info("alertsTopic is: {}", alertsTopic);
        String windowSize = System.getenv("WINDOW_SIZE_MILLISECONDS");
        if (windowSize == null) {
            windowSize = "200"; // Default value if environment variable is not set
        }
        LOG.info("windowSize is: {}", windowSize);
        String watermarkIdle = System.getenv("WATERMARK_IDLE_MILLISECONDS");
        if (watermarkIdle == null) {
            watermarkIdle = DEFAULT_IDLE_MS;
        }
        LOG.info("watermarkIdle is: {}", watermarkIdle);
        final long idleMillis = Long.parseLong(watermarkIdle);
        final Integer alertTimeout = AlertTimeout.parse(System.getenv(AlertTimeout.ENV_VARIABLE));
        LOG.info("alertTimeout is: {}", alertTimeout == null ? "Alerta default" : alertTimeout);

        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(1);
        env.getConfig().setAutoWatermarkInterval(100);
        final String tableDefinition = loadResourceFile("table_definition.sql");

        // Load SQL statements
        final String sqlStatements = loadResourceFile("sql_statements.sql");

        // Kafka Source
        final KafkaSource<KeyValueRecord> kafkaSource = KafkaSource.<KeyValueRecord>builder()
                .setBootstrapServers(kafkaBootstrap)
                .setTopics(alertsBulkTopic)
                .setGroupId("flink_json_key_reader2")
                .setStartingOffsets(OffsetsInitializer.latest())
                .setDeserializer(new KeyValueRecordDeserializer())
                .build();

        // Kafka Sink
        final KafkaSink<KeyValueRecord> kafkaSink = KafkaSink.<KeyValueRecord>builder()
                .setBootstrapServers(kafkaBootstrap)
                .setRecordSerializer(new KeyValueRecordSerializer(alertsTopic)) // directly pass your custom serializer
                .build();

        // Create a StreamTableEnvironment
        final EnvironmentSettings settings = EnvironmentSettings.newInstance()
                .inStreamingMode()
                .build();
        final StreamTableEnvironment tableEnv = StreamTableEnvironment.create(env, settings);

        // Register the DataStream as a Table
        final DataStream<KeyValueRecord> kafkaStream = env.fromSource(kafkaSource, WatermarkStrategy.<KeyValueRecord>forMonotonousTimestamps()
                // only important when kafka partitions do not map
                .withIdleness(Duration.ofSeconds(1)), "Kafka Source");

        // Apply the table definition
        LOG.info("Executing table definitions.");
        // Replace "my-cluster-kafka-bootstrap:9092" with kafkaBootstrap
        final String tblDefRepl = tableDefinition.replace("my-cluster-kafka-bootstrap:9092", kafkaBootstrap); 
        final String[] tableDefList = tblDefRepl.split(";");
        for (final String tableDef : tableDefList) {
            if (!tableDef.trim().isEmpty()) {
                LOG.info("Executing table definition: {}", tableDef);
                tableEnv.executeSql(tableDef + ';');
                registerWatermarkedViews(tableEnv, idleMillis);
            }
        }

        // Apply the SQL statements
        LOG.info("Adding SQL statements to joint pipeline.");

        final StreamStatementSet stmtSet = tableEnv.createStatementSet();
        for (final String stmt : sqlStatements.split(";")) {
            final String stmtTrimmed = stmt.trim();
            if (stmtTrimmed.toUpperCase().startsWith("INSERT")) {
                stmtSet.addInsertSql(stmtTrimmed + ";");
            } else if (!stmtTrimmed.isEmpty()) {
                // e.g. additional DDL or other statements
                tableEnv.executeSql(stmtTrimmed + ";");
            }   
        }
        //tableEnv.executeSql(sqlStatements);

        // Continue with the existing DataStream pipeline
        kafkaStream
        .filter(kv -> kv != null && kv.key != null && !kv.getKey().getEvent().equals("heartbeat"))
        .keyBy(kv -> kv.getStringKey())
        .window(EventTimeSessionWindows.withGap(Duration.ofMillis(Integer.parseInt(windowSize))))
        .reduce((e1, e2) -> e2)
        .keyBy(KeyValueRecord::getStringKey)
        .filter(new AlertsFilter())
        // After the filter, so the timeout never takes part in change detection.
        .map(new AlertTimeout(alertTimeout))
                .sinkTo(kafkaSink);

        LOG.info("Attaching Statements to DataStream Pipeline: {}", stmtSet);
        stmtSet.attachAsDataStream();
        env.execute("Core Services");
    }

    /**
     * Registers the watermarked view of every source of
     * {@link #WINDOWED_SOURCES} that exists and has no view yet. Called after
     * each table definition, so a later view of table_definition.sql can read it.
     */
    public static void registerWatermarkedViews(final StreamTableEnvironment tableEnv, final long idleMillis) {
        for (final Map.Entry<String, ChangelogMode> source : WINDOWED_SOURCES.entrySet()) {
            final String view = source.getKey().substring(0, source.getKey().length() - SOURCE_SUFFIX.length());
            final java.util.List<String> tables = Arrays.asList(tableEnv.listTables());
            if (tables.contains(source.getKey()) && !tables.contains(view)) {
                if (LOG.isInfoEnabled()) {
                    LOG.info("Registering {} over {} with the idle catch-up watermark", view, source.getKey());
                }
                IdleCatchUpWatermarks.register(tableEnv, source.getKey(), view, source.getValue(),
                        IdleCatchUpWatermarks.strategy(idleMillis));
            }
        }
    }

    public static String loadResourceFile(final String fileName) {
        try (InputStream inputStream = CoreServices.class.getClassLoader().getResourceAsStream(fileName);
                Scanner scanner = new Scanner(inputStream, StandardCharsets.UTF_8.name())) {
            return scanner.useDelimiter("\\A").next();
        } catch (Exception e) {
            throw new RuntimeException("Failed to load resource file: " + fileName, e);
        }
    }
}

package org.industryfusion;

import org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema;
import org.apache.kafka.clients.producer.ProducerRecord;

public class KeyValueRecordSerializer implements KafkaRecordSerializationSchema<KeyValueRecord> {
    private final String topic;

    public KeyValueRecordSerializer(final String topic) {
        this.topic = topic;
    }

    @Override
    public ProducerRecord<byte[], byte[]> serialize(final KeyValueRecord element,
                                                    final KafkaRecordSerializationSchema.KafkaSinkContext context,
                                                    final Long timestamp) {
        final byte[] keyBytes = element.getKey().serialize();
        byte[] valueBytes = null;
        if (element.getValue() != null) {
            valueBytes = element.getValue().serialize();
        }
        return new ProducerRecord<>(topic, keyBytes, valueBytes);
    }
}

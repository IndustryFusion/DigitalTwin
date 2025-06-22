package org.industryfusion;

import org.apache.flink.connector.kafka.source.reader.deserializer.KafkaRecordDeserializationSchema;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.flink.util.Collector;

import java.nio.charset.StandardCharsets;

import org.apache.flink.api.common.typeinfo.TypeInformation;

@SuppressWarnings("PMD.AtLeastOneConstructor")
public class KeyValueRecordDeserializer implements KafkaRecordDeserializationSchema<KeyValueRecord> {

    /**
     * Deserialize a Kafka record into a KeyValueRecord.
     * The key is deserialized into an AlertKeyObject and the value into an AlertValueObject.
     * If the key's environment is null, it is set to "Development" by default.
     * If the value is null, a default AlertValueObject is created with severity "ok" and text "Ok".
     *
     * @param record The Kafka record to deserialize.
     * @param result    The collector to output the deserialized KeyValueRecord.
     */

    @Override
    public void deserialize(final ConsumerRecord<byte[], byte[]> record, final Collector<KeyValueRecord> result) {
        AlertKeyObject key = null;
        AlertValueObject value = null;
        try {
            if (record.key() != null) {
                key = new com.fasterxml.jackson.databind.ObjectMapper().readValue(record.key(), AlertKeyObject.class);
                if (key.getEnvironment() == null) {
                    key.setEnvironment("Development"); // Default value if environment is null
                }
            }
            if (record.value() != null) {
                value = new com.fasterxml.jackson.databind.ObjectMapper().readValue(record.value(), AlertValueObject.class);
            }
            if (value == null) {
                value = new AlertValueObject(key.getResource(), key.getEvent(), key.getEnvironment());
                value.setSeverity("ok");
                value.setText("Ok");
            }
        } catch (Exception e) {
            throw new RuntimeException("Failed to deserialize key or value", e);
        }
        result.collect(new KeyValueRecord(key, value, new String(record.key(), StandardCharsets.UTF_8)));
    }

    @Override
    public TypeInformation<KeyValueRecord> getProducedType() {
        return TypeInformation.of(KeyValueRecord.class);
    }
}


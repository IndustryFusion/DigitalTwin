package org.industryfusion;

import org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.industryfusion.*;


class KeyValueRecordSerializerTest {

    @Test
    void testSerializeWithNonNullValue() {
        String topic = "test-topic";
        KeyValueRecordSerializer serializer = new KeyValueRecordSerializer(topic);

        KeyValueRecord keyValueRecord = mock(KeyValueRecord.class);
        AlertKeyObject alertKey = mock(AlertKeyObject.class);
        AlertValueObject alertValue = mock(AlertValueObject.class);
        byte[] keyBytes = {1, 2, 3};
        byte[] valueBytes = {4, 5, 6};

        when(keyValueRecord.getKey()).thenReturn(alertKey);
        when(keyValueRecord.getValue()).thenReturn(alertValue);
        when(alertKey.serialize()).thenReturn(keyBytes);
        when(alertValue.serialize()).thenReturn(valueBytes);
        KafkaRecordSerializationSchema.KafkaSinkContext context = mock(KafkaRecordSerializationSchema.KafkaSinkContext.class);

        ProducerRecord<byte[], byte[]> record = serializer.serialize(keyValueRecord, context, 123L);

        assertEquals(topic, record.topic());
        assertArrayEquals(keyBytes, record.key());
        assertArrayEquals(valueBytes, record.value());
    }

    @Test
    void testSerializeWithNullValue() {
        String topic = "test-topic";
        KeyValueRecordSerializer serializer = new KeyValueRecordSerializer(topic);

        KeyValueRecord keyValueRecord = mock(KeyValueRecord.class);
        AlertKeyObject alertKey = mock(AlertKeyObject.class);

        byte[] keyBytes = {7, 8, 9};

        when(keyValueRecord.getKey()).thenReturn(alertKey);
        when(keyValueRecord.getValue()).thenReturn(null);
        when(alertKey.serialize()).thenReturn(keyBytes);

        KafkaRecordSerializationSchema.KafkaSinkContext context = mock(KafkaRecordSerializationSchema.KafkaSinkContext.class);

        ProducerRecord<byte[], byte[]> record = serializer.serialize(keyValueRecord, context, 123L);

        assertEquals(topic, record.topic());
        assertArrayEquals(keyBytes, record.key());
        assertNull(record.value());
    }

    @Test
    void testConstructorSetsTopic() {
        String topic = "another-topic";
        KeyValueRecordSerializer serializer = new KeyValueRecordSerializer(topic);
        // Reflection to check private field 'topic'
        try {
            java.lang.reflect.Field topicField = KeyValueRecordSerializer.class.getDeclaredField("topic");
            topicField.setAccessible(true);
            assertEquals(topic, topicField.get(serializer));
        } catch (Exception e) {
            fail("Reflection failed: " + e.getMessage());
        }
    }
}
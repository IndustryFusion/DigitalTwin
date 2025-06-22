package org.industryfusion;

import org.apache.flink.util.Collector;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.industryfusion.*;





class KeyValueRecordDeserializerTest {

    private final KeyValueRecordDeserializer deserializer = new KeyValueRecordDeserializer();
    private final ObjectMapper objectMapper = new ObjectMapper();

    static class TestCollector<T> implements Collector<T> {
        List<T> collected = new ArrayList<>();
        @Override
        public void collect(T record) {
            collected.add(record);
        }
        @Override
        public void close() {}
    }

    @Test
    void testDeserializeWithValidKeyAndValue() throws Exception {
        AlertKeyObject keyObj = new AlertKeyObject();
        keyObj.setResource("res1");
        keyObj.setEvent("evt1");
        keyObj.setEnvironment("Production");
        byte[] keyBytes = objectMapper.writeValueAsBytes(keyObj);

        AlertValueObject valueObj = new AlertValueObject("res1", "evt1", "Production");
        valueObj.setSeverity("critical");
        valueObj.setText("Something happened");
        byte[] valueBytes = objectMapper.writeValueAsBytes(valueObj);

        ConsumerRecord<byte[], byte[]> record = new ConsumerRecord<>("topic", 0, 0L, keyBytes, valueBytes);
        TestCollector<KeyValueRecord> collector = new TestCollector<>();

        deserializer.deserialize(record, collector);

        assertEquals(1, collector.collected.size());
        KeyValueRecord result = collector.collected.get(0);
        assertEquals("res1", result.getKey().getResource());
        assertEquals("evt1", result.getKey().getEvent());
        assertEquals("Production", result.getKey().getEnvironment());
        assertEquals("critical", result.getValue().getSeverity());
        assertEquals("Something happened", result.getValue().getText());
    }

    @Test
    void testDeserializeWithNullEnvironmentInKey() throws Exception {
        AlertKeyObject keyObj = new AlertKeyObject();
        keyObj.setResource("res2");
        keyObj.setEvent("evt2");
        keyObj.setEnvironment(null);
        byte[] keyBytes = objectMapper.writeValueAsBytes(keyObj);

        AlertValueObject valueObj = new AlertValueObject("res2", "evt2", null);
        valueObj.setSeverity("warning");
        valueObj.setText("Check this");
        byte[] valueBytes = objectMapper.writeValueAsBytes(valueObj);

        ConsumerRecord<byte[], byte[]> record = new ConsumerRecord<>("topic", 0, 0L, keyBytes, valueBytes);
        TestCollector<KeyValueRecord> collector = new TestCollector<>();

        deserializer.deserialize(record, collector);

        assertEquals(1, collector.collected.size());
        KeyValueRecord result = collector.collected.get(0);
        assertEquals("Development", result.getKey().getEnvironment());
    }

    @Test
    void testDeserializeWithNullValue() throws Exception {
        AlertKeyObject keyObj = new AlertKeyObject();
        keyObj.setResource("res3");
        keyObj.setEvent("evt3");
        keyObj.setEnvironment("Test");
        byte[] keyBytes = objectMapper.writeValueAsBytes(keyObj);

        ConsumerRecord<byte[], byte[]> record = new ConsumerRecord<>("topic", 0, 0L, keyBytes, null);
        TestCollector<KeyValueRecord> collector = new TestCollector<>();

        deserializer.deserialize(record, collector);

        assertEquals(1, collector.collected.size());
        KeyValueRecord result = collector.collected.get(0);
        assertEquals("ok", result.getValue().getSeverity());
        assertEquals("Ok", result.getValue().getText());
        assertEquals("res3", result.getValue().getResource());
        assertEquals("evt3", result.getValue().getEvent());
        assertEquals("Test", result.getValue().getEnvironment());
    }

    @Test
    void testDeserializeWithInvalidKey() {
        byte[] invalidKey = "not-json".getBytes(StandardCharsets.UTF_8);
        byte[] valueBytes = null;
        ConsumerRecord<byte[], byte[]> record = new ConsumerRecord<>("topic", 0, 0L, invalidKey, valueBytes);
        TestCollector<KeyValueRecord> collector = new TestCollector<>();

        RuntimeException ex = assertThrows(RuntimeException.class, () -> {
            deserializer.deserialize(record, collector);
        });
        assertTrue(ex.getMessage().contains("Failed to deserialize key or value"));
    }

    @Test
    void testDeserializeWithNullKey() {
        ConsumerRecord<byte[], byte[]> record = new ConsumerRecord<>("topic", 0, 0L, null, null);
        TestCollector<KeyValueRecord> collector = new TestCollector<>();

        RuntimeException ex = assertThrows(RuntimeException.class, () -> {
            deserializer.deserialize(record, collector);
        });
        assertTrue(ex.getMessage().contains("Failed to deserialize key or value"));
    }
}
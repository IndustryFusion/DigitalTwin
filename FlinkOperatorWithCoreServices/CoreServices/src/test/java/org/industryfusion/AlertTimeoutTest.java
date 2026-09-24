package org.industryfusion;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AlertTimeoutTest {

    @Test
    void unsetMeansNeverExpire() {
        assertEquals(Integer.valueOf(0), AlertTimeout.parse(null));
    }

    @Test
    void emptyMeansAlertaDefault() {
        assertNull(AlertTimeout.parse(""));
        assertNull(AlertTimeout.parse("   "));
    }

    @Test
    void numberIsTakenAsSeconds() {
        assertEquals(Integer.valueOf(0), AlertTimeout.parse("0"));
        assertEquals(Integer.valueOf(86400), AlertTimeout.parse(" 86400 "));
    }

    @Test
    void invalidValuesAreRejected() {
        assertThrows(IllegalArgumentException.class, () -> AlertTimeout.parse("-1"));
        assertThrows(IllegalArgumentException.class, () -> AlertTimeout.parse("1d"));
        assertThrows(IllegalArgumentException.class, () -> AlertTimeout.parse("never"));
    }

    @Test
    void mapStampsTimeoutOnValue() {
        AlertValueObject value = new AlertValueObject("urn:cutter:1", "CountConstraintComponent(x)", "Development");
        value.setSeverity("warning");
        KeyValueRecord record = new KeyValueRecord(new AlertKeyObject(), value, "key");

        KeyValueRecord result = new AlertTimeout(0).map(record);

        assertEquals(Integer.valueOf(0), result.getValue().getTimeout());
        assertEquals("warning", result.getValue().getSeverity());
    }

    @Test
    void mapStampsTimeoutOnSynthesizedOk() {
        // A tombstone becomes severity "ok" in KeyValueRecordDeserializer; it
        // passes through the same stage.
        AlertValueObject value = new AlertValueObject("urn:cutter:1", "CountConstraintComponent(x)", "Development");
        value.setSeverity("ok");
        KeyValueRecord record = new KeyValueRecord(new AlertKeyObject(), value, "key");

        assertEquals(Integer.valueOf(3600), new AlertTimeout(3600).map(record).getValue().getTimeout());
    }

    @Test
    void mapToleratesMissingValue() {
        KeyValueRecord record = new KeyValueRecord(new AlertKeyObject(), null, "key");
        assertSame(record, new AlertTimeout(0).map(record));
        assertNull(record.getValue());
    }

    @Test
    void serializedAlertCarriesTimeout() throws Exception {
        AlertValueObject value = new AlertValueObject("urn:cutter:1", "CountConstraintComponent(x)", "Development");
        value.setTimeout(0);
        String json = new String(value.serialize(), java.nio.charset.StandardCharsets.UTF_8);
        assertTrue(json.contains("\"timeout\":0"), json);
    }

    @Test
    void serializedAlertOmitsTimeoutWhenNull() throws Exception {
        AlertValueObject value = new AlertValueObject("urn:cutter:1", "CountConstraintComponent(x)", "Development");
        String json = new String(value.serialize(), java.nio.charset.StandardCharsets.UTF_8);
        assertFalse(json.contains("timeout"), json);
    }
}

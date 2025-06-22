package org.industryfusion;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import org.industryfusion.*;
import java.lang.String;


class AlertKeyObjectTest {

    @Test
    void testSetEnvironmentUpdatesEnvironment() {
        AlertKeyObject alertKey = new AlertKeyObject("resource1", "event1", "Production");
        alertKey.setEnvironment("Staging");
        assertEquals("Staging", alertKey.getEnvironment());
    }

    @Test
    void testSetEnvironmentWithNull() {
        AlertKeyObject alertKey = new AlertKeyObject("resource2", "event2", "QA");
        alertKey.setEnvironment(null);
        assertNull(alertKey.getEnvironment());
    }

    @Test
    void testSetEnvironmentWithEmptyString() {
        AlertKeyObject alertKey = new AlertKeyObject("resource3", "event3", "Development");
        alertKey.setEnvironment("");
        assertEquals("", alertKey.getEnvironment());
    }
    @Test
    void testSetResourceUpdatesResource() {
        AlertKeyObject alertKey = new AlertKeyObject("resource1", "event1", "Development");
        alertKey.setResource("newResource");
        assertEquals("newResource", alertKey.getResource());
    }

    @Test
    void testSetEventUpdatesEvent() {
        AlertKeyObject alertKey = new AlertKeyObject("resource1", "event1", "Development");
        alertKey.setEvent("newEvent");
        assertEquals("newEvent", alertKey.getEvent());
    }

    @Test
    void testSerialize() {
        AlertKeyObject alertKey = new AlertKeyObject("resource1", "event1", "Development");
        byte[] serializedData = alertKey.serialize();
        assertNotNull(serializedData);
        assertTrue(serializedData.length > 0);
        // Additional checks can be done here to verify the content of serializedData
        // Convert byte[] to String and check JSON structure
        String json = new String(serializedData);
        assertTrue(json.contains("\"resource\":\"resource1\""));
        assertTrue(json.contains("\"event\":\"event1\""));
        assertTrue(json.contains("\"environment\":\"Development\""));
    } 
}
package org.industryfusion;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import org.industryfusion.*;
import java.lang.String;


class AlertValueObjectTest {

    @Test
    void getServiceReturnsNullWhenServiceIsNull() {
        AlertValueObject avo = new AlertValueObject();
        assertNull(avo.getService(), "getService() should return null when service is null");
    }

    @Test
    void getServiceReturnsCloneOfArray() {
        AlertValueObject avo = new AlertValueObject();
        String[] services = {"service1", "service2"};
        avo.setService(services);

        String[] result = avo.getService();
        assertArrayEquals(services, result, "getService() should return an array equal to the original");

        // Ensure it's a clone, not the same reference
        assertNotSame(services, result, "getService() should return a clone, not the same array");
    }

    @Test
    void modifyingReturnedArrayDoesNotAffectOriginal() {
        AlertValueObject avo = new AlertValueObject();
        String[] services = {"service1", "service2"};
        avo.setService(services);

        String[] result = avo.getService();
        result[0] = "changed";

        String[] resultAfterChange = avo.getService();
        assertEquals("service1", resultAfterChange[0], "Modifying the returned array should not affect the internal array");
    }
    //add tests for setServerity, setText, setEnvironment, setResource, setCustomer

    @Test
    void setSeveritySetsSeverity() {
        AlertValueObject avo = new AlertValueObject();
        avo.setSeverity("critical");
        assertEquals("critical", avo.getSeverity(), "setSeverity should set the severity field");
    }

    @Test
    void setTextSetsText() {
        AlertValueObject avo = new AlertValueObject();
        avo.setText("Alert triggered");
        assertEquals("Alert triggered", avo.getText(), "setText should set the text field");
    }

    @Test
    void setEnvironmentSetsEnvironment() {
        AlertValueObject avo = new AlertValueObject();
        avo.setEnvironment("Production");
        assertEquals("Production", avo.getEnvironment(), "setEnvironment should set the environment field");
    }

    @Test
    void setResourceSetsResource() {
        AlertValueObject avo = new AlertValueObject();
        avo.setResource("resource-1");
        assertEquals("resource-1", avo.getResource(), "setResource should set the resource field");
    }

    @Test
    void setCustomerSetsCustomer() {
        AlertValueObject avo = new AlertValueObject();
        avo.setCustomer("customer-xyz");
        assertEquals("customer-xyz", avo.getCustomer(), "setCustomer should set the customer field");
    }
    // and now test the serialization
    @Test
    void testSerialize() {
        AlertValueObject avo = new AlertValueObject();
        avo.setSeverity("critical");
        avo.setText("Alert triggered");
        avo.setEnvironment("Production");
        avo.setResource("resource-1");
        avo.setCustomer("customer-xyz");
        avo.setService(new String[]{"service1", "service2"});

        byte[] serializedData = avo.serialize();
        assertNotNull(serializedData);
        assertTrue(serializedData.length > 0);

        String json = new String(serializedData);
        assertTrue(json.contains("\"severity\":\"critical\""));
        assertTrue(json.contains("\"text\":\"Alert triggered\""));
        assertTrue(json.contains("\"environment\":\"Production\""));
        assertTrue(json.contains("\"resource\":\"resource-1\""));
        assertTrue(json.contains("\"customer\":\"customer-xyz\""));
        assertTrue(json.contains("\"service\":[\"service1\",\"service2\"]"));
    }
}
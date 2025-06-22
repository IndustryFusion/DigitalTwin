package org.industryfusion;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import org.industryfusion.*;
import org.industryfusion.AlertKeyObject;
import java.lang.String;
import static org.mockito.Mockito.mock;


class KeyValueRecordTest {

    @Test
    void testGetKeyReturnsSetKey() {
        AlertKeyObject mockKey = mock(AlertKeyObject.class);
        AlertValueObject mockValue = mock(AlertValueObject.class);
        KeyValueRecord record = new KeyValueRecord(mockKey, mockValue, "testKey");

        assertSame(mockKey, record.getKey());
    }

    @Test
    void testGetKeyWhenKeyIsNull() {
        KeyValueRecord record = new KeyValueRecord(null, null, null);

        assertNull(record.getKey());
    }

    @Test
    void testSetKeyAndGetKey() {
        KeyValueRecord record = new KeyValueRecord();
        AlertKeyObject mockKey = mock(AlertKeyObject.class);

        record.setKey(mockKey);

        assertSame(mockKey, record.getKey());
    }
}
package org.industryfusion;

import org.apache.flink.api.common.functions.RichFilterFunction;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.operators.StreamFilter;
import org.apache.flink.streaming.util.KeyedOneInputStreamOperatorTestHarness;
import org.apache.flink.api.java.typeutils.TypeExtractor;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.api.java.functions.KeySelector;
import org.junit.Before;
import org.junit.Test;
import org.industryfusion.*;

import static org.junit.Assert.*;

public class AlertsFilterTest {

    private KeyedOneInputStreamOperatorTestHarness<String, KeyValueRecord, KeyValueRecord> harness;

    @Before
    public void setup() throws Exception {
        // instantiate your filter
        AlertsFilter filter = new AlertsFilter();

        // wrap it in Flink's StreamFilter operator
        StreamFilter<KeyValueRecord> op = new StreamFilter<>(filter);

        // create a keyed test harness, keying on whatever KeyValueRecord::getKey returns
        harness = new KeyedOneInputStreamOperatorTestHarness<>(
            op,
            (KeySelector<KeyValueRecord, String>) KeyValueRecord::getStringKey,
            Types.STRING
        );

        // open() calls filter.open(..) under the hood and wires up state backends
        harness.open();
    }

    @Test
    public void testFirstEmitted_thenFiltered_thenEmittedOnChange() throws Exception {
        // — first element for key="A" → lastSeverity/text are null → passes filter → output
        AlertKeyObject Akey = new AlertKeyObject("resource", "Event", "environment");
        AlertValueObject Avalue = new AlertValueObject("resource", "Event", "environment");
        Avalue.setSeverity("HIGH");
        Avalue.setText("foo");
        KeyValueRecord rec1 = makeRecord(Akey, Avalue, "key");
        harness.processElement(rec1, /* timestamp */ 1L);
        assertEquals(
            "first element should be emitted",
            1,
            harness.getOutput().size()
        );
        harness.getOutput().clear();

        

        KeyValueRecord rec2 = makeRecord(Akey, Avalue, "key");
        harness.processElement(rec2, 2L);
        assertTrue(
            "same severity+text should not emit",
            harness.getOutput().isEmpty()
        );

        AlertValueObject Bvalue = new AlertValueObject("resource", "Event", "environment");
        Bvalue.setSeverity("LOW");
        Bvalue.setText("foo");
        KeyValueRecord rec3 = makeRecord(Akey, Bvalue, "key");
        harness.processElement(rec3, 3L);
        assertEquals(
            "changed severity should emit",
            1,
            harness.getOutput().size()
        );
        harness.getOutput().clear();

        AlertValueObject Cvalue = new AlertValueObject("resource", "Event", "environment");
        Cvalue.setSeverity("LOWHIGH");
        Cvalue.setText("foobar");
        KeyValueRecord rec4 = makeRecord(Akey, Cvalue, "key");
        harness.processElement(rec4, 4L);
        assertEquals(
            "changed text should emit",
            1,
            harness.getOutput().size()
        );
        harness.getOutput().clear();

        KeyValueRecord rec5 = makeRecord(Akey, Cvalue, "key2");
        harness.processElement(rec5, 5L);
        assertEquals(
            "changed text should emit",
            1,
            harness.getOutput().size()
        );
        harness.getOutput().clear();

        KeyValueRecord rec6 = makeRecord(Akey, Bvalue, "key");
        harness.processElement(rec6, 6L);
        assertEquals(
            "changed text should emit",
            1,
            harness.getOutput().size()
        );
        harness.getOutput().clear();
        KeyValueRecord rec7 = makeRecord(Akey, Cvalue, "key2");
        harness.processElement(rec7, 7L);
        assertTrue(
            "changed text should not emit",
            harness.getOutput().isEmpty()
        );
        harness.getOutput().clear();
        KeyValueRecord rec8 = makeRecord(Akey, Bvalue, "key");
        harness.processElement(rec8, 8L);
        assertTrue(
            "changed text should not emit",
            harness.getOutput().isEmpty()
        );
        harness.getOutput().clear();
    }

    /**
     * Helper to construct a KeyValueRecord.  
     * Replace the body of this with whatever your real constructor is.
     */
    private KeyValueRecord makeRecord(AlertKeyObject key, AlertValueObject value, String stringkey) {
        // e.g. if your KeyValueRecord has a constructor (String key, AlertValue val):
        // AlertValue v = new AlertValue(severity, text);
        // return new KeyValueRecord(key, v);

        // or if it’s built differently, swap in the correct code here:
        return new KeyValueRecord(key, value, stringkey);
    }
}

package org.industryfusion;

import org.apache.flink.api.common.functions.RichFilterFunction;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.configuration.Configuration;

@SuppressWarnings("PMD.AtLeastOneConstructor")
public class AlertsFilter extends  RichFilterFunction<KeyValueRecord> {
    private transient ValueState<String> lastSeverity;
    private transient ValueState<String> lastText;

    @Override
    public void open(final Configuration parameters) {
        // initialize per-key state to hold the previous severity
        lastSeverity = getRuntimeContext().getState(
            new ValueStateDescriptor<>("lastSeverity", String.class)
        );
        lastText = getRuntimeContext().getState(
            new ValueStateDescriptor<>("lastText", String.class)
        );
    }

    @Override
    public boolean filter(final KeyValueRecord keyvalue) throws Exception {

        // compare current vs. previous severity and text
        final String prevSeverity = lastSeverity.value();
        final String currentSeverity = keyvalue.getValue().getSeverity();
        final String prevText = lastText.value();
        final String currentText = keyvalue.getValue().getText();
        final boolean changed = prevSeverity == null || !prevSeverity.equals(currentSeverity)  || !prevText.equals(currentText);

        // update state for next time
        lastSeverity.update(currentSeverity);
        lastText.update(currentText);

        return changed;
    }
}
package org.industryfusion;

import org.apache.flink.api.common.functions.MapFunction;

/**
 * Stamps the Alerta timeout onto every forwarded alert.
 *
 * AlertsFilter forwards an alert only when its severity or text changes, so a
 * violation that stays true reaches Alerta exactly once. With Alerta's default
 * timeout (86400 s) such an alert expires a day later and housekeeping deletes
 * it, while the validation behind it is still firing. A timeout of 0 tells
 * Alerta never to expire it; it then stays open until a clear arrives.
 */
@SuppressWarnings("PMD.AtLeastOneConstructor")
public class AlertTimeout implements MapFunction<KeyValueRecord, KeyValueRecord> {
    private static final long serialVersionUID = 1L;

    /** Environment variable holding the timeout in seconds. */
    public static final String ENV_VARIABLE = "ALERTA_TIMEOUT";

    /** Used when ENV_VARIABLE is not set: never expire. */
    public static final int DEFAULT_TIMEOUT = 0;

    private final Integer timeout;

    public AlertTimeout(final Integer timeout) {
        this.timeout = timeout;
    }

    /**
     * Parses the configured timeout.
     *
     * @param value the raw setting; null when the variable is not set
     * @return DEFAULT_TIMEOUT when unset, null when set but empty (the alert
     *         then carries no timeout and Alerta applies its own default),
     *         otherwise the number of seconds
     * @throws IllegalArgumentException when the value is neither empty nor a
     *         non-negative integer, so a typo fails the submission instead of
     *         silently changing when alerts expire
     */
    public static Integer parse(final String value) {
        Integer seconds = null;
        if (value == null) {
            seconds = DEFAULT_TIMEOUT;
        } else if (!value.trim().isEmpty()) {
            try {
                seconds = Integer.valueOf(value.trim());
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException(ENV_VARIABLE + " must be a non-negative integer, got: " + value, e);
            }
            if (seconds < 0) {
                throw new IllegalArgumentException(ENV_VARIABLE + " must be a non-negative integer, got: " + value);
            }
        }
        return seconds;
    }

    @Override
    public KeyValueRecord map(final KeyValueRecord record) {
        if (record.getValue() != null) {
            record.getValue().setTimeout(timeout);
        }
        return record;
    }
}

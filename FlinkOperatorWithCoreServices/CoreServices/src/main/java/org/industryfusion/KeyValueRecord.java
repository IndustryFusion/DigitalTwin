package org.industryfusion;

public class KeyValueRecord {
    public AlertKeyObject key;
    public AlertValueObject value;
    public String stringKey;

    public KeyValueRecord() {}

    public KeyValueRecord(final AlertKeyObject key, final AlertValueObject value, final String stringKey) {
        this.key = key;
        this.value = value;
        this.stringKey = stringKey;
    }

    public AlertKeyObject getKey() {
        return key;
    }
    public AlertValueObject getValue() {
        return value;
    }
    public void setKey(final AlertKeyObject key) {
        this.key = key;
    }
    public void setValue(final AlertValueObject value) {
        this.value = value;
    }
    public String getStringKey() {
        return stringKey;
    }
    @Override
    public String toString() {
        return "KeyValueRecord{key='" + key + "', value='" + value + "'}";
    }
}

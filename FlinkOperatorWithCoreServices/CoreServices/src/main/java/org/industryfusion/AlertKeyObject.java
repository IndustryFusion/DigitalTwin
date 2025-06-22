package org.industryfusion;

import com.fasterxml.jackson.annotation.JsonPropertyOrder;

@JsonPropertyOrder({ "resource", "event", "environment", "service", "severity", "customer", "text" })
public class AlertKeyObject {
/**
 * This class represents the key for an alert row in Kubernetes, containing resource, event, and environment.
 */
    public String resource;
    public String event;
    public String environment;
    public AlertKeyObject() {} // required for Jackson
    @Override
    public String toString() {
        return "AlertKeyObject{" +
                "resource='" + resource + '\'' +
                ", event='" + event + '\'' +
                ", environment='" + environment ;
    }
    // Remove @Nullable if you do not have the annotation available, or ensure the correct import is present
    public AlertKeyObject(final String resource, final String event, final String environment) {
        this.resource = resource;
        this.event = event;
        this.environment = (environment != null) ? environment : "Development";
    }
    public void setEnvironment(final String environment) {
        this.environment = environment;
    }
    public String getEnvironment() {
        return environment;
    }
    public String getResource() {
        return resource;
    }
    public String getEvent() {
        return event;
    }
    public void setResource(final String resource) {
        this.resource = resource;
    }
    public void setEvent(final String event) {
        this.event = event;
    }
    public byte[] serialize() {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsBytes(this);
        } catch (Exception e) {
            throw new RuntimeException("Failed to serialize AlertKeyObject", e);
        }
    }
}

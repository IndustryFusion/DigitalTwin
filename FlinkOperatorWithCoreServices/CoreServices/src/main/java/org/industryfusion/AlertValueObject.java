package org.industryfusion;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonPropertyOrder({ "resource", "event", "environment", "service", "severity", "customer", "text" })
public class AlertValueObject {
    public String resource;
    public String event;
    public String environment;
    public String severity;
    public String text;
    public String[] service;
    public String customer;
    public AlertValueObject() {} // required for Jackson
  
    public AlertValueObject(final String resource, final String event, final String environment) {
        this.resource = resource;
        this.event = event;
        this.environment = (environment != null) ? environment : "Development";
        String customer = System.getenv("ALERTA_CUSTOMER");
        if (customer == null ) {
            customer = "customer"; // Default value if environment variable is not set
        }
        this.customer = customer;
    }
    public String getResource() {
        return resource;
    }
    public String getEvent() {
        return event;
    }
    public String getEnvironment() {
        return environment;
    }
    public String getSeverity() {
        return severity;
    }
    public String getText() {
        return text;
    }
    public String[] getService() {
        return service == null
            ? null
            : service.clone();
    }
    public String getCustomer() {
        return customer;
    }
    public void setResource(final String resource) {
        this.resource = resource;
    }
    public void setEvent(final String event) {
        this.event = event;
    }
    public void setEnvironment(final String environment) {
        this.environment = environment;
    }
    public void setSeverity(final String severity) {
        this.severity = severity;
    }
    public void setText(final String text) {
        this.text = text;
    }
    public void setService(final String... service) {
        // defensive copy still works, since varargs are just an array at runtime
        this.service = (service == null) ? null : service.clone();
    }
    public void setCustomer(final String customer) {
        this.customer = customer;
    }
    public byte[] serialize() {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsBytes(this);
        } catch (Exception e) {
            throw new RuntimeException("Failed to serialize AlertValueObject", e);
        }
    }
}

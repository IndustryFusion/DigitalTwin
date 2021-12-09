package adapter.service;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;
import java.util.HashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.json.simple.JSONArray;
import org.json.simple.JSONObject;
import org.json.simple.parser.JSONParser;
import java.util.Iterator;
import org.apache.kafka.common.KafkaException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.messaging.handler.annotation.Payload;

@Service
public class DebeziumProcessor {

    @Autowired
    KafkaTemplate<String, Object> KafkaJsontemplate;

    @Value("${spring.kafka.consumer.group-id}")
    private String consumergroup;

    public JSONParser parser = new JSONParser();
    private final static Logger logger = LoggerFactory.getLogger(DebeziumProcessor.class);

    /*
     * Kafka Producer
     */
    private void send(JSONObject entity, String topic) throws KafkaException {
        logger.info("Publishing in topic " + topic);
        KafkaJsontemplate.send(topic.toLowerCase(), entity);
    }

    /*
     * Kafka Consumer
     */
    @KafkaListener(topics = "#{'${spring.kafka.consumer.topic}'}", groupId = "#{'${spring.kafka.consumer.group-id}'}", containerFactory = "kafkaListener")
    public void consume(@Payload(required = false) JSONObject entity) throws Exception {
        if (entity != null) {
            logger.trace("Payload received ");
            entity = processDebeziumData(entity);
            String output_topic = "entity_";
            if (entity.get("after") != null) {
                output_topic += (String) ((JSONObject) entity.get("after")).get("type");
            } else if (entity.get("before") != null) {
                output_topic += (String) ((JSONObject) entity.get("before")).get("type");
            } else {
                output_topic += "errors";
            }
            send(entity, output_topic);
        }
    }

    /*
     * Method to get key value pair from debezium json
     */
    public JSONObject processDebeziumData(JSONObject entity) {
        try {
            if (!entity.get("after").equals(null))
                entity.put("after", processEntity((HashMap<String, Object>) entity.get("after")));
        } catch (Exception e) {
            logger.error("'after' field is null");
        }
        try {
            if (!entity.get("before").equals(null))
                entity.put("before", processEntity((HashMap<String, Object>) entity.get("before")));
        } catch (Exception e) {
            logger.error("'before' field is null");
        }
        return entity;
    }

    /*
     * Method to get key value pair from a debezium json feild.
     */
    protected JSONObject processEntity(HashMap<String, Object> fieldjson) throws Exception {
        logger.debug("Payload processing started :: " + fieldjson.get("id"));
        JSONObject requiredfield = new JSONObject();
        requiredfield.put("id", (String) fieldjson.get("id"));
        if (fieldjson.get("type") != null)
            requiredfield.put("type", resolve((String) fieldjson.get("type")));
        if (fieldjson.get("context") != null) {
            requiredfield.put("@context", parser.parse((String) fieldjson.get("context")));
        }
        if (fieldjson.get("kvdata") == null)
            return requiredfield;
        JSONObject kvjson = (JSONObject) parser.parse((String) fieldjson.get("kvdata"));
        kvjson.remove("@id");
        kvjson.remove("@type");
        JSONArray newarray;
        for (Iterator keys = kvjson.keySet().iterator(); keys.hasNext();) {
            String key = (String) keys.next();
            logger.debug("Processing Payload key " + key);
            if (kvjson.get(key).getClass().getSimpleName().equals("String")) {
                newarray = processString((String) kvjson.get(key));
                requiredfield.put(resolve(key), ((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else if (kvjson.get(key).getClass().getSimpleName().equals("JSONArray")) {
                newarray = processArray((JSONArray) kvjson.get(key));
                requiredfield.put(resolve(key), ((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else if (kvjson.get(key).getClass().getSimpleName().equals("JSONObject")) {
                newarray = processObject((JSONObject) kvjson.get(key));
                requiredfield.put(resolve(key), ((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else {
                requiredfield.put(resolve(key), kvjson.get(key));
            }
        }
        logger.debug("Payload processing completed :: " + fieldjson.get("id"));
        return requiredfield;
    }

    /*
     * Method to fetch the values from json string
     */
    private JSONArray processString(String objstr) {
        logger.trace("inside processString()");
        JSONArray result = new JSONArray();
        try {
            Object obj = parser.parse(objstr);
            JSONArray newarray;
            if (obj.getClass().getSimpleName().equals("JSONArray")) {
                newarray = processArray((JSONArray) obj);
                result.add(((newarray.size() == 1) ? newarray.get(0) : newarray));
            }
            if (obj.getClass().getSimpleName().equals("JSONObject")) {
                newarray = processObject((JSONObject) obj);
                result.add(((newarray.size() == 1) ? newarray.get(0) : newarray));
            }
        } catch (Exception e) {
            result.add(objstr);
        }
        logger.trace("processString() completed");
        return result;
    }

    /*
     * Method to fetch the values from json object
     */
    private JSONArray processObject(JSONObject obj) {
        logger.trace("inside processObject()");
        JSONArray result = new JSONArray();
        JSONArray newarray;
        for (Iterator keys = obj.keySet().iterator(); keys.hasNext();) {
            String key = (String) keys.next();
            String resolvekey = resolve(key);
            if (resolvekey.equals("type") || resolvekey.equals("createdAt") || resolvekey.equals("modifiedAt")) {
                continue;
            } else if (obj.get(key).getClass().getSimpleName().equals("String")) {
                newarray = processString((String) obj.get(key));
                result.add(((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else if (obj.get(key).getClass().getSimpleName().equals("JSONArray")) {
                newarray = processArray((JSONArray) obj.get(key));
                result.add(((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else if (obj.get(key).getClass().getSimpleName().equals("JSONObject")) {
                newarray = processObject((JSONObject) obj.get(key));
                result.add(((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else {
                result.add(obj.get(key));
            }
        }
        logger.trace("processObject() completed");
        return result;
    }

    /*
     * Method to fetch the values from json array
     */
    private JSONArray processArray(JSONArray array) {
        logger.trace("inside processArray()");
        JSONArray result = new JSONArray();
        JSONArray newarray;
        for (int i = 0; i < array.size(); i++) {
            if (array.get(i).getClass().getSimpleName().equals("String")) {
                newarray = processString((String) array.get(i));
                result.add(((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else if (array.get(i).getClass().getSimpleName().equals("JSONArray")) {
                newarray = processArray((JSONArray) array.get(i));
                result.add(((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else if (array.get(i).getClass().getSimpleName().equals("JSONObject")) {
                newarray = processObject((JSONObject) array.get(i));
                result.add(((newarray.size() == 1) ? newarray.get(0) : newarray));
            } else {
                result.add(array.get(i));
            }
        }
        logger.trace("processArray() completed");
        return result;
    }

    /*
     * Method to fetch the type , relationship
     */
    private String resolve(String key) {
        String key_list[] = key.split("(:)|(#)|(/)|(@)|(//)");
        String new_key = key_list[key_list.length - 1];
        return new_key;
    }
}

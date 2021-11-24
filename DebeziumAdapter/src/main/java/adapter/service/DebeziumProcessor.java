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
import java.util.Set;
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
            } else if (entity.get("before") != null)
                output_topic += (String) ((JSONObject) entity.get("before")).get("type");
            else
                output_topic += "errors";
            send(entity, output_topic);
        }
    }

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
     * Method to get key value pair from debezium json
     */
    protected JSONObject processEntity(HashMap<String, Object> fieldjson) throws Exception {
        logger.debug("Payload processing started :: " + fieldjson.get("id"));
        JSONObject requiredfield = new JSONObject();
        requiredfield.put("id", (String) fieldjson.get("id"));
        if (fieldjson.get("type") != null)
            requiredfield.put("type", resolve((String) fieldjson.get("type")));
        if (fieldjson.get("context") != null) {
            String context = (String) fieldjson.get("context");
            requiredfield.put("@context", parser.parse(context));
        }
        if (fieldjson.get("kvdata") == null)
            return requiredfield;
        JSONObject kvjson = (JSONObject) parser.parse((String) fieldjson.get("kvdata"));
        kvjson.remove("@id");
        kvjson.remove("@type");
        for (Iterator keys = kvjson.keySet().iterator(); keys.hasNext();) {
            String key = (String) keys.next();
            logger.debug("Processing Payload key " + key);
            if (kvjson.get(key).getClass().getSimpleName().equals("String")) {
                requiredfield.put(resolve(key), kvjson.get(key));
            } else if (kvjson.get(key).getClass().getSimpleName().equals("JSONArray")) {
                JSONArray newarray = processArray((JSONArray) kvjson.get(key));
                if (newarray.size() == 1)
                    requiredfield.put(resolve(key), newarray.get(0));
                else
                    requiredfield.put(resolve(key), newarray);
            } else {
                requiredfield.put(resolve(key), kvjson.get(key));
            }
        }
        logger.debug("Payload processing completed :: " + fieldjson.get("id"));
        return requiredfield;
    }

    /*
     * Method to fetch the values from json array
     */
    private JSONArray processArray(JSONArray array) {
        logger.trace("inside processArray()");
        JSONArray newarray = new JSONArray();
        for (int i = 0; i < array.size(); i++) {
            if (array.get(i).getClass().getSimpleName().equals("String")) {
                newarray.add(resolve((String) array.get(i)));
            } else if (array.get(i).getClass().getSimpleName().equals("JSONObject")) {
                JSONObject tmp = (JSONObject) array.get(i);
                tmp = resolveObject(tmp);
                for (Iterator tmpkeys = tmp.keySet().iterator(); tmpkeys.hasNext();) {
                    String itrkey = (String) tmpkeys.next();
                    try {
                        JSONObject obj1 = (JSONObject) parser.parse((String) tmp.get(itrkey));
                        obj1 = resolveObject(obj1);
                        int size = obj1.keySet().size();
                        if (size == 1)
                            newarray.add(obj1.values().iterator().next());
                        else
                            newarray.add(obj1.values());
                    } catch (Exception e) {
                        newarray.add(tmp.get(itrkey));
                    }
                }
            } else {
                newarray.add(array.get(i));
            }
        }
        logger.trace("processArray() completed");
        return newarray;
    }

    /*
     * Method to make JSONObject simple
     */
    private JSONObject resolveObject(JSONObject obj) {
        Set objkeys = obj.keySet();
        if (objkeys.contains("type"))
            obj.remove("type");
        if (objkeys.contains("@type"))
            obj.remove("@type");
        if (objkeys.contains("createdAt"))
            obj.remove("createdAt");
        if (objkeys.contains("@createdAt"))
            obj.remove("@createdAt");
        if (objkeys.contains("modifiedAt"))
            obj.remove("modifiedAt");
        if (objkeys.contains("@modifiedAt"))
            obj.remove("@modifiedAt");
        return obj;
    }

    /*
     * Method to fetch the type , relationship
     */
    private String resolve(String key) {
        String key_list[] = key.split("(:)|(#)|(/)|(@)");
        String new_key = key_list[key_list.length - 1];
        return new_key;
    }
}

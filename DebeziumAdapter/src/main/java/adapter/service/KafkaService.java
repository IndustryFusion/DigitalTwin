package adapter.service;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;
import java.util.Iterator;
import org.json.simple.JSONArray;
import org.json.simple.JSONObject;
import org.json.simple.parser.JSONParser;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class KafkaService {

    @Autowired
    KafkaTemplate<String,Object> KafkaJsontemplate;

    @Value("${spring.kafka.consumer.group-id}")
    private String consumergroup;

    public JSONParser parser = new JSONParser();
    private final static Logger logger = LoggerFactory.getLogger(KafkaService.class);

    @KafkaListener(topics = "#{'${spring.kafka.consumer.topic}'}" ,
    groupId = "#{'${spring.kafka.consumer.group-id}'}" ,containerFactory = "kafkaListener")
    public void consume(String entity) throws Exception{

        logger.trace("consume() :: started");
        JSONObject entity_json = (JSONObject) parser.parse(entity);
        String output_topic = "entity_";

        try{
            if(entity_json.get("after") != null)
                entity_json.put("after",processEntity((JSONObject)entity_json.get("after")));

            output_topic += (String)((JSONObject)entity_json.get("after")).get("type");
        }
        catch(Exception e)
        { logger.trace("after field is null");}

        try{
            if(entity_json.get("before") != null)
                entity_json.put("before",processEntity((JSONObject)entity_json.get("before")));
            
            if(output_topic == "entity_")
                output_topic += (String)((JSONObject)entity_json.get("before")).get("type");
        }
        catch(Exception e)
        { logger.trace("before field is null");}

        output_topic = output_topic.toLowerCase();

        logger.trace(" publishing final results in  : "+output_topic);
        KafkaJsontemplate.send(output_topic,entity_json);

        logger.trace("consume :: completed");
    }

    /*
        Method to fetch the entity type, relationship 
    */
    private String resolve(String key){
        
        String key_list[] = key.split("(:)|(#)|(/)|(@)");
        String new_key = key_list[key_list.length-1];
        return new_key;
    }

    /*
        Method to get key value pair from debezium json 
    */  
    private JSONObject processEntity(JSONObject field_json) throws Exception{

        logger.trace(" processEntity :: started");

        if(field_json.equals(null))
            return null;

        JSONObject processed_field = new JSONObject();

        processed_field.put("id", (String)field_json.get("id"));

        if(field_json.get("type") != null)
            processed_field.put("type" , resolve((String)field_json.get("type")));

        if(field_json.get("kvdata") == null)
            return processed_field;

        
        String kvdata_str = (String)field_json.get("kvdata");
        JSONObject kvdata_json = (JSONObject) parser.parse(kvdata_str);        


        for(Iterator keys = kvdata_json.keySet().iterator(); keys.hasNext();) {

            String key = (String)keys.next();
            if( !key.equals("@id") && !key.equals("@type")){

                String value_type = kvdata_json.get(key).getClass().getSimpleName();

                if(value_type.equals("String")){
                    processed_field.put(resolve(key) , kvdata_json.get(key));
                }
                else if(value_type.equals("JSONArray")){
                    
                    JSONArray new_array = processArray((JSONArray)kvdata_json.get(key));

                    if(new_array.size() == 1)
                        processed_field.put(resolve(key) , new_array.get(0));
                    else
                        processed_field.put(resolve(key) , new_array);//recent update
                    
                }
                else{
                    processed_field.put(resolve(key) , kvdata_json.get(key));
                }
                
            }
        }
        
        logger.trace("processEntity :: completed");
        return processed_field;
    }


    /*
        Method to fetch the values from json array
    */
    private JSONArray processArray(JSONArray array){

        logger.trace("processArray :: started");
        JSONArray new_array = new JSONArray();

        for(int i = 0; i < array.size(); i++)
        {
            String arr_value_type = array.get(i).getClass().getSimpleName();

            if(arr_value_type.equals("String")){

                new_array.add(resolve((String)array.get(i)));
            }
            else if(arr_value_type.equals("JSONArray")){
                new_array.add((JSONArray)array.get(i));
            }
            else if(arr_value_type.equals("JSONObject")){

                JSONObject tmp = (JSONObject)array.get(i);
                Iterator tmp_keys = tmp.keySet().iterator();

                while(tmp_keys.hasNext()){
                    String itr_key = (String)tmp_keys.next();

                    if(resolve(itr_key).equals("type") || resolve(itr_key).equals("createdAt") || resolve(itr_key).equals("modifiedAt")){
                        continue;
                    }
                    else{
                        String type_t = tmp.get(itr_key).getClass().getSimpleName();
                        if(type_t.equals("String")){
                            try{
                                JSONObject obj1=(JSONObject)parser.parse((String)tmp.get(itr_key));
                                Iterator obj1_keys = obj1.keySet().iterator();
                                while(obj1_keys.hasNext()){
                                    String obj1_key = (String)obj1_keys.next();
                                    if(obj1_key.equals("type")|| obj1_key.equals("createdAt") || obj1_key.equals("modifiedAt"))
                                        continue;
                                    else
                                        new_array.add(obj1.get(obj1_key));
                                }
                                
                            }catch(Exception e){
                                new_array.add(tmp.get(itr_key));
                            }
                        }
                        else
                            new_array.add(tmp.get(itr_key));
                    }
                }

            }
            
        }

        logger.trace("processArray :: completed");
        return new_array;
    }

}
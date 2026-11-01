package tn.tunicheque.notification_service.config;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import tn.tunicheque.notification_service.kafka.ChequeEvent;

import java.util.HashMap;
import java.util.Map;

@Configuration
public class KafkaConsumerConfig {

    @Value("${spring.kafka.bootstrap-servers:localhost:9092}")
    private String bootstrapServers;

    // ── Factory pour ChequeEvent (topics existants) ───────────────

    @Bean
    public ConsumerFactory<String, ChequeEvent> consumerFactory() {
        JsonDeserializer<ChequeEvent> deser = new JsonDeserializer<>(ChequeEvent.class);
        deser.addTrustedPackages("*");
        deser.setUseTypeMapperForKey(false);

        Map<String, Object> props = baseConsumerProps();
        return new DefaultKafkaConsumerFactory<>(props, new StringDeserializer(), deser);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, ChequeEvent>
            kafkaListenerContainerFactory() {
        ConcurrentKafkaListenerContainerFactory<String, ChequeEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory());
        factory.setConcurrency(2);
        return factory;
    }

    // ── Factory pour Map (topics réclamation) ─────────────────────

    @Bean
    public ConsumerFactory<String, Map> mapConsumerFactory() {
        JsonDeserializer<Map> deser = new JsonDeserializer<>(Map.class);
        deser.addTrustedPackages("*");
        Map<String, Object> props = baseConsumerProps();
        return new DefaultKafkaConsumerFactory<>(props, new StringDeserializer(), deser);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, Map>
            mapKafkaListenerContainerFactory() {
        ConcurrentKafkaListenerContainerFactory<String, Map> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(mapConsumerFactory());
        factory.setConcurrency(2);
        return factory;
    }

    // ── Propriétés communes (latence réduite) ──────────────────────

    private Map<String, Object> baseConsumerProps() {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,   bootstrapServers);
        props.put(ConsumerConfig.GROUP_ID_CONFIG,             "notification-group");
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,    "earliest");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        // Réduire la latence de polling : fetch dès que 1 message disponible (max 100ms d'attente)
        props.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG,      1);
        props.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG,    100);
        props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG,     10);
        return props;
    }
}

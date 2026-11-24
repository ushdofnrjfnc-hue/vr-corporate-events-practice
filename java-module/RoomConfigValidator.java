import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * RoomConfigValidator - вспомогательный модуль на Java
 * для проверки корректности JSON-конфигурации виртуальной комнаты.
 *
 * Используется на серверной стороне перед сохранением конфигурации,
 * созданной Python-модулем VirtualRoomBuilder.to_json().
 *
 * Требует библиотеку org.json (доступна через Maven Central).
 * Компиляция: javac -cp json.jar RoomConfigValidator.java
 * Запуск:    java -cp .:json.jar RoomConfigValidator
 */
public class RoomConfigValidator {

    private final List<String> errors;

    public RoomConfigValidator() {
        this.errors = new ArrayList<>();
    }

    /**
     * Проверка корректности JSON-конфигурации комнаты.
     * @param configJson строка с JSON
     * @return true, если конфигурация валидна
     */
    public boolean validate(String configJson) {
        errors.clear();

        if (configJson == null || configJson.isEmpty()) {
            errors.add("Пустая конфигурация");
            return false;
        }

        try {
            JSONObject config = new JSONObject(configJson);

            validateRequiredString(config, "room_name");
            validateRequiredString(config, "lighting_type");
            validateRequiredInt(config, "capacity");

            if (config.has("capacity")) {
                int capacity = config.getInt("capacity");
                if (capacity < 1 || capacity > 100) {
                    errors.add("Вместимость должна быть от 1 до 100, получено: " + capacity);
                }
            }

            if (config.has("lighting_intensity")) {
                double intensity = config.getDouble("lighting_intensity");
                if (intensity < 0.0 || intensity > 1.0) {
                    errors.add("Интенсивность освещения должна быть от 0.0 до 1.0, получено: " + intensity);
                }
            }

            if (config.has("objects")) {
                JSONArray objects = config.getJSONArray("objects");
                for (int i = 0; i < objects.length(); i++) {
                    JSONObject obj = objects.getJSONObject(i);
                    validateRequiredString(obj, "name");
                    validateRequiredString(obj, "model_path");
                }
            }

        } catch (Exception e) {
            errors.add("Ошибка парсинга JSON: " + e.getMessage());
        }

        return errors.isEmpty();
    }

    /**
     * Получить список найденных ошибок валидации.
     */
    public List<String> getErrors() {
        return new ArrayList<>(errors);
    }

    private void validateRequiredString(JSONObject obj, String field) {
        if (!obj.has(field) || obj.getString(field).isEmpty()) {
            errors.add("Отсутствует обязательное поле: " + field);
        }
    }

    private void validateRequiredInt(JSONObject obj, String field) {
        if (!obj.has(field)) {
            errors.add("Отсутствует обязательное поле: " + field);
        }
    }

    /**
     * Тестовый запуск.
     */
    public static void main(String[] args) {
        RoomConfigValidator validator = new RoomConfigValidator();

        String validConfig = "{\"room_name\":\"test\"," +
                "\"lighting_type\":\"bright\"," +
                "\"lighting_intensity\":0.8," +
                "\"capacity\":10," +
                "\"objects\":[{\"name\":\"table\"," +
                "\"model_path\":\"models/table.obj\"}]}";

        String invalidConfig = "{\"room_name\":\"\"," +
                "\"lighting_type\":\"bright\"," +
                "\"lighting_intensity\":1.5," +
                "\"capacity\":150," +
                "\"objects\":[]}";

        System.out.println("Валидная конфигурация: " + validator.validate(validConfig));
        System.out.println("Ошибки: " + validator.getErrors());

        System.out.println("\nНевалидная конфигурация: " + validator.validate(invalidConfig));
        System.out.println("Ошибки: " + validator.getErrors());
    }
}
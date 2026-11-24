"""
vr_oop.py
Объектно-ориентированная реализация модуля организации
корпоративных мероприятий в виртуальной реальности.
Этап 4 учебной практики. Группа ИКБО-30-24.

Содержит классы:
- DatabaseError, ValidationError - пользовательские исключения
- LightingType, RoomTemplate - перечисления
- Vector3, VRObject, VirtualRoomConfig - классы данных
- InvitationManager - управление приглашениями
- VirtualRoomBuilder - конструктор виртуальных комнат
- PollManager - система голосований
"""

import secrets
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Tuple, Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


# ============================================================
# Исключения
# ============================================================

class DatabaseError(Exception):
    """Ошибка при работе с базой данных."""
    pass


class ValidationError(Exception):
    """Ошибка валидации входных данных."""
    pass


# ============================================================
# Перечисления
# ============================================================

class LightingType(Enum):
    BRIGHT = "bright"
    DIM = "dim"
    NATURAL = "natural"


class RoomTemplate(Enum):
    CONFERENCE_ROOM = "conference_room"
    OPEN_SPACE = "open_space"
    AUDITORIUM = "auditorium"


# ============================================================
# Классы данных
# ============================================================

@dataclass
class Vector3:
    """Трёхмерный вектор положения, вращения или масштаба."""
    x: float
    y: float
    z: float


@dataclass
class VRObject:
    """Объект в виртуальной реальности."""
    name: str
    model_path: str
    position: Vector3
    rotation: Vector3
    scale: Vector3
    material: str = "default"


@dataclass
class VirtualRoomConfig:
    """Полная конфигурация виртуальной комнаты."""
    room_name: str
    dimensions: Vector3
    lighting_intensity: float
    lighting_type: str
    color_scheme: Dict[str, str]
    objects: List[VRObject] = field(default_factory=list)
    spawn_points: List[Vector3] = field(default_factory=list)
    capacity: int = 0


# ============================================================
# Класс InvitationManager
# ============================================================

class InvitationManager:
    """
    Менеджер приглашений на мероприятия.
    Отвечает за генерацию токенов доступа и их проверку.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        if db_connection is None:
            raise DatabaseError("Подключение к базе данных не может быть None")
        self.db = db_connection

    def generate_invitation_token(
        self,
        event_id: int,
        user_id: int,
        expiration_hours: int = 72
    ) -> Tuple[str, datetime]:
        """
        Алгоритм 1: генерация уникального токена доступа.
        Сложность: O(1).
        """
        if event_id < 0 or user_id < 0:
            raise ValidationError("event_id и user_id не могут быть отрицательными")

        try:
            current_time = datetime.now()
            expires_at = current_time + timedelta(hours=expiration_hours)

            # Криптографически стойкая случайная строка (32 hex-символа)
            token = secrets.token_hex(16)

            # SHA-256 хеш только от токена
            token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()

            cursor = self.db.cursor()
            cursor.execute(
                """
                INSERT INTO invitations
                (token_hash, event_id, user_id, expires_at, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (
                    token_hash,
                    event_id,
                    user_id,
                    expires_at.isoformat(),
                    current_time.isoformat()
                )
            )
            self.db.commit()
            return token, expires_at

        except sqlite3.Error as e:
            self.db.rollback()
            raise DatabaseError(f"Ошибка записи в базу данных: {e}") from e

    def verify_invitation_token(
        self,
        token: str,
        event_id: int
    ) -> Dict[str, Any]:
        """
        Алгоритм 2: проверка валидности токена.
        Сложность: O(log n) при наличии индекса по token_hash.

        Исправление по рецензии: два UPDATE объединены в один
        с использованием COALESCE для сохранения accepted_at.
        """
        current_time = datetime.now()

        try:
            token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()

            cursor = self.db.cursor()
            cursor.execute(
                """
                SELECT id, user_id, status, expires_at
                FROM invitations
                WHERE token_hash = ? AND event_id = ?
                """,
                (token_hash, event_id)
            )

            invitation = cursor.fetchone()

            if not invitation:
                return {
                    'access_granted': False,
                    'error_message': 'Неверный токен или мероприятие'
                }

            inv_id, user_id, status, expires_at_str = invitation

            # Парсинг строки даты обратно в datetime
            expires_at = datetime.fromisoformat(expires_at_str)

            if status == 'revoked':
                return {
                    'access_granted': False,
                    'error_message': 'Приглашение отозвано организатором'
                }

            if current_time > expires_at:
                return {
                    'access_granted': False,
                    'error_message': 'Срок действия приглашения истек'
                }

            # Исправление по рецензии: один UPDATE вместо двух
            cursor.execute(
                """
                UPDATE invitations
                SET status = 'joined',
                    accepted_at = COALESCE(accepted_at, ?),
                    joined_at = ?
                WHERE id = ?
                """,
                (current_time.isoformat(), current_time.isoformat(), inv_id)
            )
            self.db.commit()

            return {
                'access_granted': True,
                'user_id': user_id
            }

        except sqlite3.Error as e:
            self.db.rollback()
            return {
                'access_granted': False,
                'error_message': f'Ошибка базы данных: {e}'
            }


# ============================================================
# Класс VirtualRoomBuilder
# ============================================================

class VirtualRoomBuilder:
    """
    Конструктор виртуальных комнат.
    Алгоритм 3: построение конфигурации комнаты из шаблона.
    Сложность: O(c), где c - вместимость.
    """

    TEMPLATES = {
        RoomTemplate.CONFERENCE_ROOM: {
            'base_dimensions': Vector3(10, 8, 3),
            'base_objects': [
                VRObject(
                    "conference_table", "models/table.obj",
                    Vector3(0, 0, 0), Vector3(0, 0, 0), Vector3(1, 1, 1)
                ),
                VRObject(
                    "main_screen", "models/screen.obj",
                    Vector3(0, -3, 1.5), Vector3(0, 90, 0), Vector3(1, 1, 0.1)
                ),
            ],
            'default_materials': {
                'walls': '#E0E0E0',
                'floor': '#404040',
                'furniture': '#8B4513'
            }
        },
        RoomTemplate.OPEN_SPACE: {
            'base_dimensions': Vector3(15, 15, 4),
            'base_objects': [],
            'default_materials': {
                'walls': '#F5F5F5',
                'floor': '#808080',
                'furniture': '#000000'
            }
        },
        RoomTemplate.AUDITORIUM: {
            'base_dimensions': Vector3(20, 15, 5),
            'base_objects': [
                VRObject(
                    "stage", "models/stage.obj",
                    Vector3(0, 7, 0), Vector3(0, 0, 0), Vector3(1, 1, 1)
                ),
            ],
            'default_materials': {
                'walls': '#2C2C2C',
                'floor': '#1A1A1A',
                'furniture': '#8B0000'
            }
        }
    }

    COLOR_SCHEMES = {
        'corporate': {
            'walls': '#4A90E2', 'floor': '#2C3E50', 'furniture': '#34495E'
        },
        'warm': {
            'walls': '#F5E6D3', 'floor': '#8B7355', 'furniture': '#D2691E'
        },
        'modern': {
            'walls': '#FFFFFF', 'floor': '#1C1C1C', 'furniture': '#FF6B6B'
        },
        'nature': {
            'walls': '#E8F5E9', 'floor': '#5D4037', 'furniture': '#388E3C'
        }
    }

    def build_room(
        self,
        template_type: RoomTemplate,
        capacity: int,
        lighting: LightingType,
        color_scheme: str,
        additional_objects: Optional[List[Dict]] = None
    ) -> VirtualRoomConfig:
        """Построение конфигурации виртуальной комнаты."""
        if capacity < 1 or capacity > 100:
            raise ValidationError("Вместимость должна быть от 1 до 100")

        template = self.TEMPLATES.get(template_type)
        if template is None:
            raise ValidationError(f"Неизвестный шаблон: {template_type}")

        # Масштабирование по вместимости
        space_per_person = 2.5
        required_space = capacity * space_per_person
        base_dims = template['base_dimensions']
        scale_factor = (required_space / (base_dims.x * base_dims.y)) ** 0.5

        dimensions = Vector3(
            base_dims.x * scale_factor,
            base_dims.y * scale_factor,
            base_dims.z
        )

        lighting_intensity = self._get_lighting_intensity(lighting)
        colors = self._apply_color_scheme(color_scheme, template['default_materials'])

        objects = self._copy_base_objects(template['base_objects'], scale_factor, colors)
        objects.extend(
            self._create_seating(capacity, template_type, dimensions)
        )

        if additional_objects:
            objects.extend(self._add_custom_objects(additional_objects))

        spawn_points = self._create_spawn_points(capacity, dimensions)

        return VirtualRoomConfig(
            room_name=f"{template_type.value}_{capacity}persons",
            dimensions=dimensions,
            lighting_intensity=lighting_intensity,
            lighting_type=lighting.value,
            color_scheme=colors,
            objects=objects,
            spawn_points=spawn_points,
            capacity=capacity
        )

    def _get_lighting_intensity(self, lighting: LightingType) -> float:
        intensities = {
            LightingType.BRIGHT: 1.0,
            LightingType.DIM: 0.5,
            LightingType.NATURAL: 0.8
        }
        return intensities.get(lighting, 0.8)

    def _apply_color_scheme(
        self,
        scheme_name: str,
        defaults: Dict[str, str]
    ) -> Dict[str, str]:
        return self.COLOR_SCHEMES.get(scheme_name, defaults)

    def _copy_base_objects(
        self,
        base_objects: List[VRObject],
        scale_factor: float,
        colors: Dict[str, str]
    ) -> List[VRObject]:
        result = []
        for obj in base_objects:
            result.append(VRObject(
                name=obj.name,
                model_path=obj.model_path,
                position=obj.position,
                rotation=obj.rotation,
                scale=Vector3(
                    obj.scale.x * scale_factor,
                    obj.scale.y * scale_factor,
                    obj.scale.z
                ),
                material=colors['furniture']
            ))
        return result

    def _create_seating(
        self,
        capacity: int,
        room_type: RoomTemplate,
        dimensions: Vector3
    ) -> List[VRObject]:
        """
        Создание мест для участников.
        Исправление по рецензии: ровно capacity стульев,
        распределённых по обе стороны стола.
        """
        import math
        seats = []

        if room_type == RoomTemplate.CONFERENCE_ROOM:
            # Чётные индексы - верхняя сторона, нечётные - нижняя
            # Для нечётного количества верхняя сторона получает на 1 стул больше
            top_side = (capacity + 1) // 2
            bottom_side = capacity // 2
        
            for i in range(top_side):
                seats.append(VRObject(
                    name=f"chair_top_{i}",
                    model_path="models/chair.obj",
                    position=Vector3(i * 0.6, 3.5, 0),
                    rotation=Vector3(0, 180, 0),
                    scale=Vector3(1, 1, 1),
                    material="default"
                ))
        
            for i in range(bottom_side):
                seats.append(VRObject(
                    name=f"chair_bottom_{i}",
                    model_path="models/chair.obj",
                    position=Vector3(i * 0.6, 2.5, 0),
                    rotation=Vector3(0, 0, 0),
                    scale=Vector3(1, 1, 1),
                    material="default"
                ))

        elif room_type == RoomTemplate.AUDITORIUM:
            rows = max(1, capacity // 10)
            seats_per_row = max(1, capacity // rows)
            placed = 0

            for row in range(rows):
                for seat in range(seats_per_row):
                    if placed >= capacity:
                        break
                    seats.append(VRObject(
                        name=f"seat_{row}_{seat}",
                        model_path="models/auditorium_seat.obj",
                        position=Vector3(
                            (seat - seats_per_row / 2) * 0.6,
                            5 + row * 1.5,
                            0.5 + row * 0.3
                        ),
                        rotation=Vector3(0, 0, 0),
                        scale=Vector3(1, 1, 1),
                        material="default"
                    ))
                    placed += 1

        else:  # OPEN_SPACE
            for i in range(capacity):
                angle = (i / capacity) * 2 * math.pi
                radius = 5
                seats.append(VRObject(
                    name=f"spot_{i}",
                    model_path="models/floor_marker.obj",
                    position=Vector3(
                        radius * math.cos(angle),
                        radius * math.sin(angle),
                        0
                    ),
                    rotation=Vector3(0, 0, 0),
                    scale=Vector3(0.5, 0.5, 0.5),
                    material="default"
                ))

        return seats

    def _create_spawn_points(
        self,
        capacity: int,
        dimensions: Vector3
    ) -> List[Vector3]:
        spawn_points = []
        perimeter = 2 * (dimensions.x + dimensions.z)
        spacing = perimeter / max(1, capacity)

        for i in range(min(capacity, 20)):
            position = (i * spacing) % perimeter

            if position < dimensions.x:
                x = position - dimensions.x / 2
                z = -dimensions.z / 2 - 1
            elif position < dimensions.x + dimensions.z:
                x = dimensions.x / 2 + 1
                z = (position - dimensions.x) - dimensions.z / 2
            elif position < 2 * dimensions.x + dimensions.z:
                x = dimensions.x / 2 - (position - dimensions.x - dimensions.z)
                z = dimensions.z / 2 + 1
            else:
                x = -dimensions.x / 2 - 1
                z = dimensions.z / 2 - (position - 2 * dimensions.x - dimensions.z)

            spawn_points.append(Vector3(x, 1.6, z))

        return spawn_points

    def _add_custom_objects(self, objects_data: List[Dict]) -> List[VRObject]:
        objects = []
        for obj_data in objects_data:
            objects.append(VRObject(
                name=obj_data.get('name', 'custom_object'),
                model_path=obj_data.get('model_path', 'models/box.obj'),
                position=Vector3(
                    obj_data.get('x', 0),
                    obj_data.get('z', 0),
                    obj_data.get('y', 0)
                ),
                rotation=Vector3(
                    obj_data.get('rot_x', 0),
                    obj_data.get('rot_y', 0),
                    obj_data.get('rot_z', 0)
                ),
                scale=Vector3(
                    obj_data.get('scale_x', 1),
                    obj_data.get('scale_y', 1),
                    obj_data.get('scale_z', 1)
                ),
                material=obj_data.get('material', 'default')
            ))
        return objects

    def to_json(self, config: VirtualRoomConfig) -> str:
        """Сериализация конфигурации в JSON."""
        def convert(obj):
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, '__dict__'):
                return {k: convert(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [convert(item) for item in obj]
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj

        return json.dumps(
            convert(config),
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# Класс PollManager
# ============================================================

class PollManager:
    """
    Менеджер голосований.
    Алгоритм 4: обработка голосований.
    Сложность: O(m log m), где m - количество голосов.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        if db_connection is None:
            raise DatabaseError("Подключение к базе данных не может быть None")
        self.db = db_connection

    def create_poll(
        self,
        event_id: int,
        question: str,
        options: List[str]
    ) -> int:
        if not question or not options:
            raise ValidationError("Вопрос и варианты не могут быть пустыми")
        if len(options) < 2:
            raise ValidationError("Должно быть минимум два варианта ответа")

        try:
            cursor = self.db.cursor()
            cursor.execute(
                """
                INSERT INTO polls
                (event_id, question, options_json, status, created_at)
                VALUES (?, ?, ?, 'active', ?)
                """,
                (
                    event_id,
                    question,
                    json.dumps(options, ensure_ascii=False),
                    datetime.now().isoformat()
                )
            )
            self.db.commit()
            return cursor.lastrowid

        except sqlite3.Error as e:
            self.db.rollback()
            raise DatabaseError(f"Ошибка создания голосования: {e}") from e

    def cast_vote(
        self,
        poll_id: int,
        user_id: int,
        selected_option: int
    ) -> Dict[str, Any]:
        cursor = self.db.cursor()

        try:
            # Проверка: не голосовал ли уже
            cursor.execute(
                """
                SELECT result_id FROM poll_results
                WHERE poll_id = ? AND user_id = ?
                """,
                (poll_id, user_id)
            )
            if cursor.fetchone():
                return {
                    'success': False,
                    'error': 'Пользователь уже проголосовал'
                }

            # Проверка: активно ли голосование
            cursor.execute(
                "SELECT status, options_json FROM polls WHERE poll_id = ?",
                (poll_id,)
            )
            row = cursor.fetchone()
            if not row or row[0] != 'active':
                return {'success': False, 'error': 'Голосование закрыто'}

            options = json.loads(row[1])
            if selected_option < 0 or selected_option >= len(options):
                return {
                    'success': False,
                    'error': 'Некорректный вариант ответа'
                }

            # Запись голоса
            cursor.execute(
                """
                INSERT INTO poll_results
                (poll_id, user_id, selected_option, voted_at)
                VALUES (?, ?, ?, ?)
                """,
                (poll_id, user_id, selected_option, datetime.now().isoformat())
            )
            self.db.commit()

            # Подсчёт результатов
            cursor.execute(
                """
                SELECT selected_option, COUNT(*) as cnt
                FROM poll_results
                WHERE poll_id = ?
                GROUP BY selected_option
                """,
                (poll_id,)
            )
            results = {r[0]: r[1] for r in cursor.fetchall()}

            for i in range(len(options)):
                results.setdefault(i, 0)

            return {'success': True, 'current_results': results}

        except sqlite3.Error as e:
            self.db.rollback()
            return {'success': False, 'error': f'Ошибка БД: {e}'}


# ============================================================
# Вспомогательные функции и тесты
# ============================================================

def create_test_database() -> sqlite3.Connection:
    """Создание тестовой БД со всеми таблицами."""
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE,
            event_id INTEGER,
            user_id INTEGER,
            expires_at TEXT,
            status TEXT,
            created_at TEXT,
            accepted_at TEXT,
            joined_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE polls (
            poll_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            question TEXT,
            options_json TEXT,
            status TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE poll_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER,
            user_id INTEGER,
            selected_option INTEGER,
            voted_at TEXT
        )
    """)

    db.commit()
    return db


def test_invitation_system():
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ InvitationManager (Алгоритмы 1 и 2)")
    print("=" * 60)

    db = create_test_database()
    manager = InvitationManager(db)

    print("\n[Тест 1] Генерация токена доступа")
    token, expires = manager.generate_invitation_token(100, 42)
    assert len(token) == 32
    print(f"  Токен: {token[:16]}...")
    print(f"  Срок: {expires}")
    print("  [OK]")

    print("\n[Тест 2] Проверка валидного токена")
    result = manager.verify_invitation_token(token, 100)
    assert result['access_granted'] is True
    assert result['user_id'] == 42
    print(f"  Доступ разрешён для пользователя {result['user_id']}")
    print("  [OK]")

    print("\n[Тест 3] Проверка неверного токена")
    result = manager.verify_invitation_token("wrong", 100)
    assert result['access_granted'] is False
    print(f"  Ошибка: {result['error_message']}")
    print("  [OK]")

    print("\n[Тест 4] Проверка токена для другого мероприятия")
    result = manager.verify_invitation_token(token, 999)
    assert result['access_granted'] is False
    print("  [OK]")

    print("\n[Тест 5] Валидация входных параметров")
    try:
        manager.generate_invitation_token(-1, 42)
        assert False, "Должно быть выброшено ValidationError"
    except ValidationError as e:
        print(f"  Поймано исключение: {e}")
        print("  [OK]")

    db.close()
    print("\n[OK] Все тесты InvitationManager пройдены!\n")


def test_room_builder():
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ VirtualRoomBuilder (Алгоритм 3)")
    print("=" * 60)

    builder = VirtualRoomBuilder()

    print("\n[Тест 1] Конференц-зал на 10 человек")
    config = builder.build_room(
        RoomTemplate.CONFERENCE_ROOM, 10,
        LightingType.BRIGHT, 'corporate',
        additional_objects=[{
            'name': 'whiteboard',
            'model_path': 'models/whiteboard.obj',
            'x': 4, 'z': 0, 'y': 1.5,
            'rot_x': 0, 'rot_y': 90, 'rot_z': 0,
            'scale_x': 1, 'scale_y': 1, 'scale_z': 0.1
        }]
    )
    assert config.capacity == 10
    assert len(config.spawn_points) > 0
    print(f"  Размеры: {config.dimensions.x:.2f} x {config.dimensions.z:.2f} м")
    print(f"  Объектов: {len(config.objects)}")
    print("  [OK]")

    print("\n[Тест 2] Аудитория на 30 человек")
    config = builder.build_room(
        RoomTemplate.AUDITORIUM, 30,
        LightingType.DIM, 'modern'
    )
    assert config.capacity == 30
    seats = [o for o in config.objects if 'seat' in o.name]
    assert len(seats) == 30
    print(f"  Мест создано: {len(seats)}")
    print("  [OK]")

    print("\n[Тест 3] Сериализация в JSON")
    json_str = builder.to_json(config)
    parsed = json.loads(json_str)
    assert 'room_name' in parsed
    print(f"  Размер JSON: {len(json_str)} байт")
    print("  [OK]")

    print("\n[Тест 4] Нечётное количество стульев (исправление рецензии)")
    config = builder.build_room(
        RoomTemplate.CONFERENCE_ROOM, 7,
        LightingType.BRIGHT, 'corporate'
    )
    chairs = [o for o in config.objects if 'chair' in o.name]
    assert len(chairs) == 7
    print(f"  Стульев для 7 человек: {len(chairs)}")
    print("  [OK]")

    print("\n[Тест 5] Валидация вместимости")
    try:
        builder.build_room(
            RoomTemplate.CONFERENCE_ROOM, 0,
            LightingType.BRIGHT, 'corporate'
        )
        assert False
    except ValidationError as e:
        print(f"  Поймано исключение: {e}")
        print("  [OK]")

    print("\n[OK] Все тесты VirtualRoomBuilder пройдены!\n")


def test_poll_system():
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ PollManager (Алгоритм 4)")
    print("=" * 60)

    db = create_test_database()
    poll_mgr = PollManager(db)

    print("\n[Тест 1] Создание голосования")
    poll_id = poll_mgr.create_poll(
        1, "Как вам мероприятие?",
        ["Отлично", "Хорошо", "Нормально", "Плохо"]
    )
    assert poll_id > 0
    print(f"  ID голосования: {poll_id}")
    print("  [OK]")

    print("\n[Тест 2] Голосование трёх пользователей")
    r1 = poll_mgr.cast_vote(poll_id, 1, 0)
    assert r1['success']
    r2 = poll_mgr.cast_vote(poll_id, 2, 0)
    assert r2['success']
    r3 = poll_mgr.cast_vote(poll_id, 3, 1)
    assert r3['success']
    print(f"  Результаты: {r3['current_results']}")
    print("  [OK]")

    print("\n[Тест 3] Повторное голосование запрещено")
    r4 = poll_mgr.cast_vote(poll_id, 1, 2)
    assert not r4['success']
    print(f"  Ошибка: {r4['error']}")
    print("  [OK]")

    print("\n[Тест 4] Некорректный вариант ответа")
    r5 = poll_mgr.cast_vote(poll_id, 99, 999)
    assert not r5['success']
    print(f"  Ошибка: {r5['error']}")
    print("  [OK]")

    db.close()
    print("\n[OK] Все тесты PollManager пройдены!\n")


def test_database_persistence():
    """
    Тест сохранности данных между вызовами методов.
    Добавлен по рекомендации рецензента.
    """
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ СОХРАННОСТИ ДАННЫХ (рецензия)")
    print("=" * 60)

    db = create_test_database()
    manager = InvitationManager(db)

    print("\n[Тест] Данные сохраняются между вызовами методов")
    token1, _ = manager.generate_invitation_token(100, 42)
    token2, _ = manager.generate_invitation_token(100, 43)

    # Проверяем, что оба токена работают независимо
    r1 = manager.verify_invitation_token(token1, 100)
    r2 = manager.verify_invitation_token(token2, 100)

    assert r1['access_granted'] and r1['user_id'] == 42
    assert r2['access_granted'] and r2['user_id'] == 43
    print("  Оба токена корректно сохранены и проверены")
    print("  [OK]")

    db.close()
    print("\n[OK] Тест сохранности данных пройден!\n")


# ============================================================
# Главный блок
# ============================================================

if __name__ == "__main__":
    test_invitation_system()
    test_room_builder()
    test_poll_system()
    test_database_persistence()

    print("=" * 60)
    print("ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ")
    print("=" * 60)
from dataclasses import dataclass, field
from typing import Protocol, Sequence, TypeVar, Optional, List, Dict, Any, Union
import json
import os
from abc import abstractmethod

T = TypeVar('T')


@dataclass(order=True)
class User:
    """Класс пользователя с обязательными и необязательными полями.
    Сортируется по полю name, пароль скрыт при выводе."""
    id: int
    name: str
    login: str
    password: str = field(repr=False)
    email: Optional[str] = None
    address: Union[str, None] = None  # Альтернативный вариант аннотации

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация пользователя в словарь."""
        return {
            'id': self.id,
            'name': self.name,
            'login': self.login,
            'password': self.password,
            'email': self.email,
            'address': self.address
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Десериализация пользователя из словаря."""
        return cls(
            id=data['id'],
            name=data['name'],
            login=data['login'],
            password=data['password'],
            email=data.get('email'),  # get() для обработки отсутствия ключа
            address=data.get('address')
        )


class DataRepositoryProtocol(Protocol[T]):
    """Протокол (интерфейс) для репозитория данных."""
    def get_all(self) -> Sequence[T]: ...
    def get_by_id(self, id: int) -> Optional[T]: ...
    def add(self, item: T) -> None: ...
    def update(self, item: T) -> None: ...
    def delete(self, item: T) -> None: ...


class UserRepositoryProtocol(DataRepositoryProtocol[User], Protocol):
    """Специализированный протокол для работы с пользователями."""
    def get_by_login(self, login: str) -> Optional[User]: ...


class DataRepository(DataRepositoryProtocol[T]):
    """Базовая реализация репозитория с хранением в JSON-файле."""

    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self._items: List[T] = []
        self._load()

    def _load(self) -> None:
        """Загрузка данных из файла."""
        try:
            if os.path.exists(self._file_path):
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._items = [self._deserialize(item) for item in data]
            else:
                self._items = []
        except (json.JSONDecodeError, IOError):
            self._items = []

    def _save(self) -> None:
        """Сохранение данных в файл."""
        try:
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump([self._serialize(item) for item in self._items], f, indent=2)
        except IOError as e:
            raise IOError(f"Ошибка сохранения данных: {e}")

    @abstractmethod
    def _serialize(self, item: T) -> Dict[str, Any]:
        """Абстрактный метод для сериализации элемента."""
        pass

    @abstractmethod
    def _deserialize(self, data: Dict[str, Any]) -> T:
        """Абстрактный метод для десериализации элемента."""
        pass

    def get_all(self) -> Sequence[T]:
        """Получение всех элементов."""
        return self._items.copy()

    def get_by_id(self, id: int) -> Optional[T]:
        """Получение элемента по ID."""
        try:
            return next((item for item in self._items if getattr(item, 'id') == id), None)
        except StopIteration:
            return None

    def add(self, item: T) -> None:
        """Добавление нового элемента."""
        if any(getattr(existing, 'id') == getattr(item, 'id') for existing in self._items):
            raise ValueError(f"Элемент с ID {getattr(item, 'id')} уже существует")
        self._items.append(item)
        self._save()

    def update(self, item: T) -> None:
        """Обновление существующего элемента."""
        item_id = getattr(item, 'id')
        for i, existing_item in enumerate(self._items):
            if getattr(existing_item, 'id') == item_id:
                self._items[i] = item
                self._save()
                return
        raise ValueError(f"Элемент с ID {item_id} не найден")

    def delete(self, item: T) -> None:
        """Удаление элемента."""
        item_id = getattr(item, 'id')
        initial_count = len(self._items)
        self._items = [i for i in self._items if getattr(i, 'id') != item_id]
        if len(self._items) == initial_count:
            raise ValueError(f"Элемент с ID {item_id} не найден")
        self._save()


class UserRepository(DataRepository[User], UserRepositoryProtocol):
    """Реализация репозитория для работы с пользователями."""

    def __init__(self, file_path: str = 'users.json') -> None:
        super().__init__(file_path)

    def _serialize(self, item: User) -> Dict[str, Any]:
        """Сериализация пользователя."""
        return item.to_dict()

    def _deserialize(self, data: Dict[str, Any]) -> User:
        """Десериализация пользователя."""
        try:
            return User.from_dict(data)
        except KeyError as e:
            raise ValueError(f"Некорректные данные пользователя: отсутствует ключ {e}") from e

    def get_by_login(self, login: str) -> Optional[User]:
        """Получение пользователя по логину."""
        try:
            return next((user for user in self._items if user.login == login), None)
        except StopIteration:
            return None


class AuthServiceProtocol(Protocol):
    """Протокол сервиса авторизации."""

    def sign_in(self, user: User) -> None: ...

    def sign_out(self) -> None: ...

    @property
    def is_authorized(self) -> bool:
        ...

    @property
    def current_user(self) -> Optional[User]:
        ...


class AuthService(AuthServiceProtocol):
    """Реализация сервиса авторизации с сохранением состояния."""

    _AUTH_FILE = 'auth.json'

    def __init__(self, user_repository: UserRepositoryProtocol) -> None:
        self._user_repo = user_repository
        self._current_user: Optional[User] = None
        self._auto_sign_in()

    def _auto_sign_in(self) -> None:
        """Автоматическая авторизация при запуске."""
        try:
            if os.path.exists(self._AUTH_FILE):
                with open(self._AUTH_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    user_id = data.get('user_id')
                    if user_id is not None:
                        user = self._user_repo.get_by_id(user_id)
                        if user is not None:
                            self._current_user = user
        except (json.JSONDecodeError, IOError):
            pass

    def sign_in(self, user: User) -> None:
        """Авторизация пользователя."""
        try:
            self._current_user = user
            with open(self._AUTH_FILE, 'w', encoding='utf-8') as f:
                json.dump({'user_id': user.id}, f, indent=2)
        except IOError as e:
            raise IOError(f"Ошибка сохранения состояния авторизации: {e}")

    def sign_out(self) -> None:
        """Выход из системы."""
        self._current_user = None
        try:
            if os.path.exists(self._AUTH_FILE):
                os.remove(self._AUTH_FILE)
        except IOError:
            pass

    @property
    def is_authorized(self) -> bool:
        """Проверка авторизации пользователя."""
        return self._current_user is not None

    @property
    def current_user(self) -> Optional[User]:
        """Получение текущего пользователя."""
        return self._current_user


def demo_system() -> None:
    """Демонстрация работы системы авторизации."""
    try:
        # Инициализация
        user_repo = UserRepository()
        auth_service = AuthService(user_repo)

        # Проверка на первый запуск (если нет файла пользователей)
        if not os.path.exists('users.json'):
            print("=== Первый запуск системы ===")
            print("Регистрация новых пользователей...")

            # Добавление пользователей
            users = [
                User(id=1, name="Алексей Петров", login="alex", password="qwerty", email="alex@example.com"),
                User(id=2, name="Мария Иванова", login="mary", password="12345", address="ул. Пушкина, 10")
            ]

            for user in users:
                user_repo.add(user)

            print("\nВсе зарегистрированные пользователи:")
            for user in user_repo.get_all():
                print(f"{user.id}: {user.name} ({user.login})")

            # Авторизация первого пользователя
            print("\nАвторизация пользователя alex...")
            user = user_repo.get_by_login("alex")
            if user:
                auth_service.sign_in(user)
        else:
            print("=== Повторный запуск системы ===")
            # Загрузка существующих пользователей
            user_repo._load()

            if auth_service.is_authorized:
                user = auth_service.current_user
                print(f"Добро пожаловать назад, {user.name}!")
                print(f"Ваш email: {user.email or 'не указан'}")
                print(f"Ваш адрес: {user.address or 'не указан'}")
            else:
                print("Автоматическая авторизация не выполнена. Пожалуйста, войдите вручную.")

        # Демонстрация работы с данными
        print("\n=== Работа с данными ===")
        print("Все пользователи в системе:")
        for user in user_repo.get_all():
            print(f"{user.id}: {user.name} ({user.login})")

        # Редактирование (если пользователь существует)
        user_to_update = user_repo.get_by_id(1)
        if user_to_update:
            print(f"\nРедактирование пользователя {user_to_update.name}...")
            user_to_update.name = "Алексей Николаевич Петров"
            user_repo.update(user_to_update)
            print(f"Обновленный пользователь: {user_repo.get_by_id(1)}")

        # Удаление (если пользователь существует)
        user_to_delete = user_repo.get_by_id(2)
        if user_to_delete:
            print(f"\nУдаление пользователя {user_to_delete.name}...")
            user_repo.delete(user_to_delete)

        print("\nОставшиеся пользователи:")
        for user in user_repo.get_all():
            print(f"{user.id}: {user.name}")

        # Состояние авторизации в конце
        print("\n=== Состояние системы ===")
        if auth_service.is_authorized:
            print(f"Текущий авторизованный пользователь: {auth_service.current_user.name}")
            print("При следующем запуске система попытается автоматически авторизовать этого пользователя.")
        else:
            print("Нет авторизованных пользователей.")

        print("\nДемонстрация завершена. Файлы сохранены для следующего запуска.")

    except Exception as e:
        print(f"Ошибка в демонстрационной системе: {e}")
        raise


if __name__ == "__main__":
    demo_system()

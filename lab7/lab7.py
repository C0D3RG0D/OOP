from abc import ABC, abstractmethod
from typing import Type, Dict, Any, Callable, Optional, TypeVar

# Определяем тип переменной для дженериков
T = TypeVar('T')


class LifeStyle:
    """Перечисление для стилей жизненного цикла зависимостей"""
    PerRequest = "PerRequest"  # Новый экземпляр при каждом запросе
    Scoped = "Scoped"          # Один экземпляр в пределах области видимости
    Singleton = "Singleton"    # Один экземпляр на все время работы приложения


class Injector:
    """Основной класс для управления зависимостями и их внедрения"""

    def __init__(self) -> None:
        """Инициализация инжектора"""
        self._registrations: Dict[Type, Dict[str, Any]] = {}
        self._singleton_instances: Dict[Type, Any] = {}
        self._scoped_instances: Dict[Type, Any] = {}
        self._in_scope: bool = False

    def register(
        self,
        interface_type: Type[T],
        implementation: Type[T] or Callable[..., T],
        life_style: str = LifeStyle.PerRequest,
        params: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Регистрация зависимости между интерфейсом и его реализацией

        Args:
            interface_type: Тип интерфейса (абстрактный класс)
            implementation: Класс реализации или фабричный метод
            life_style: Стиль жизненного цикла (из перечисления LifeStyle)
            params: Дополнительные параметры для конструктора или фабричного метода

        Raises:
            ValueError: Если передан некорректный тип реализации
        """
        if params is None:
            params = {}

        if not (isinstance(implementation, type) or callable(implementation)):
            raise ValueError("Implementation must be a class or callable factory method")

        registration: Dict[str, Any] = {
            'life_style': life_style,
            'params': params
        }

        if callable(implementation) and not isinstance(implementation, type):
            registration['factory'] = implementation
        else:
            registration['implementation'] = implementation

        self._registrations[interface_type] = registration

    def get_instance(self, interface_type: Type[T]) -> T:
        """
        Получение экземпляра реализации для указанного интерфейса

        Args:
            interface_type: Тип интерфейса, для которого нужно получить реализацию

        Returns:
            Экземпляр класса реализации

        Raises:
            ValueError: Если для интерфейса нет зарегистрированной реализации
            RuntimeError: При попытке получить Scoped-экземпляр вне области видимости
        """
        if interface_type not in self._registrations:
            raise ValueError(f"No registration found for {interface_type.__name__}")

        registration = self._registrations[interface_type]
        life_style = registration['life_style']

        try:
            if life_style == LifeStyle.Singleton:
                if interface_type not in self._singleton_instances:
                    self._singleton_instances[interface_type] = self._create_instance(interface_type)
                return self._singleton_instances[interface_type]

            elif life_style == LifeStyle.Scoped:
                if not self._in_scope:
                    raise RuntimeError("Cannot get scoped instance outside of a scope")

                if interface_type not in self._scoped_instances:
                    self._scoped_instances[interface_type] = self._create_instance(interface_type)
                return self._scoped_instances[interface_type]

            else:  # PerRequest
                return self._create_instance(interface_type)
        except Exception as e:
            raise RuntimeError(f"Failed to create instance of {interface_type.__name__}: {str(e)}")

    def _create_instance(self, interface_type: Type[T]) -> T:
        """
        Внутренний метод для создания экземпляра реализации

        Args:
            interface_type: Тип интерфейса

        Returns:
            Экземпляр класса реализации

        Raises:
            RuntimeError: Если не удалось создать экземпляр
        """
        registration = self._registrations[interface_type]

        try:
            if 'factory' in registration:
                # Используем фабричный метод
                factory = registration['factory']
                params = registration['params']
                return factory(**params)
            else:
                # Создаем экземпляр класса
                implementation = registration['implementation']
                params = registration['params']

                constructor_params = self._resolve_constructor_params(params)
                instance = implementation(**constructor_params)

                # Внедряем зависимости через сеттеры, если они есть
                if hasattr(instance, 'set_logger'):
                    try:
                        logger = self.get_instance(ILogger)
                        instance.set_logger(logger)
                    except (ValueError, RuntimeError):
                        pass  # Логгер не зарегистрирован - это нормально

                return instance
        except Exception as e:
            raise RuntimeError(f"Failed to create instance of {interface_type.__name__}: {str(e)}")

    def _resolve_constructor_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Разрешает зависимости в параметрах конструктора

        Args:
            params: Параметры конструктора

        Returns:
            Словарь с разрешенными параметрами
        """
        resolved_params = {}

        for param_name, param_value in params.items():
            if isinstance(param_value, str) and param_value.startswith('@'):
                # Это ссылка на другой зарегистрированный сервис
                try:
                    dependency_interface = globals()[param_value[1:]]
                    resolved_params[param_name] = self.get_instance(dependency_interface)
                except KeyError:
                    raise ValueError(f"Dependency {param_value[1:]} not found")
            else:
                # Это обычное значение параметра
                resolved_params[param_name] = param_value

        return resolved_params

    def scope(self) -> 'Scope':
        """
        Создает новую область видимости для Scoped-зависимостей

        Returns:
            Контекстный менеджер Scope
        """
        return Scope(self)


class Scope:
    """Контекстный менеджер для работы с областью видимости зависимостей"""

    def __init__(self, injector: Injector) -> None:
        self.injector = injector

    def __enter__(self) -> Injector:
        """Вход в область видимости"""
        self.injector._in_scope = True
        self.injector._scoped_instances = {}
        return self.injector

    def __exit__(self, exc_type: Optional[Type[BaseException]],
                 exc_val: Optional[BaseException],
                 exc_tb: Optional[Any]) -> None:
        """Выход из области видимости"""
        self.injector._in_scope = False
        self.injector._scoped_instances = {}


# Определение интерфейсов
class ILogger(ABC):
    """Абстрактный класс для системы логирования"""

    @abstractmethod
    def log(self, message: str) -> None:
        """Запись сообщения в лог"""
        pass


class IDatabase(ABC):
    """Абстрактный класс для работы с базой данных"""

    @abstractmethod
    def connect(self) -> None:
        """Подключение к базе данных"""
        pass

    @abstractmethod
    def query(self, sql: str) -> list[Dict[str, Any]]:
        """Выполнение SQL-запроса"""
        pass


class IEmailService(ABC):
    """Абстрактный класс для отправки email"""

    @abstractmethod
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Отправка email"""
        pass


# Реализации интерфейсов
class ConsoleLogger(ILogger):
    """Реализация логгера, выводящая сообщения в консоль"""

    def log(self, message: str) -> None:
        print(f"[LOG] {message}")


class FileLogger(ILogger):
    """Реализация логгера, записывающая сообщения в файл"""

    def __init__(self, filename: str = "app.log") -> None:
        self.filename = filename

    def log(self, message: str) -> None:
        try:
            with open(self.filename, 'a', encoding='utf-8') as f:
                f.write(f"[LOG] {message}\n")
        except IOError as e:
            print(f"Failed to write to log file: {str(e)}")


class SqlDatabase(IDatabase):
    """Реализация работы с SQL базой данных"""

    def __init__(self, connection_string: str, logger: Optional[ILogger] = None) -> None:
        self.connection_string = connection_string
        self._logger = logger

    def set_logger(self, logger: ILogger) -> None:
        """Внедрение логгера через сеттер"""
        self._logger = logger

    def connect(self) -> None:
        if self._logger:
            self._logger.log(f"Connecting to SQL database: {self.connection_string}")
        print(f"Connected to SQL database: {self.connection_string}")

    def query(self, sql: str) -> list[Dict[str, Any]]:
        if self._logger:
            self._logger.log(f"Executing SQL query: {sql}")
        print(f"Executed SQL query: {sql}")
        return [{"id": 1, "name": "Test"}]


class MockDatabase(IDatabase):
    """Mock-реализация базы данных для тестирования"""

    def connect(self) -> None:
        print("Connected to Mock database")

    def query(self, sql: str) -> list[Dict[str, Any]]:
        print(f"Mocked SQL query: {sql}")
        return [{"id": 1, "name": "Mocked"}]


class SmtpEmailService(IEmailService):
    """Реализация сервиса email через SMTP"""

    def __init__(self, smtp_server: str, smtp_port: int, logger: Optional[ILogger] = None) -> None:
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self._logger = logger

    def set_logger(self, logger: ILogger) -> None:
        """Внедрение логгера через сеттер"""
        self._logger = logger

    def send_email(self, to: str, subject: str, body: str) -> None:
        if self._logger:
            self._logger.log(f"Sending email to {to} with subject '{subject}'")
        print(f"Email sent to {to} via SMTP {self.smtp_server}:{self.smtp_port}")


class MockEmailService(IEmailService):
    """Mock-реализация сервиса email для тестирования"""

    def send_email(self, to: str, subject: str, body: str) -> None:
        print(f"Mock email sent to {to} with subject '{subject}'")


# Фабричные методы
def create_file_logger() -> ILogger:
    """Фабричный метод для создания файлового логгера с настройками"""
    return FileLogger(filename="custom.log")


# Конфигурации
def configure_dev(injector: Injector) -> None:
    """Конфигурация для режима разработки"""
    injector.register(ILogger, ConsoleLogger, LifeStyle.Singleton)
    injector.register(IDatabase, MockDatabase, LifeStyle.PerRequest)
    injector.register(IEmailService, MockEmailService, LifeStyle.Scoped)


def configure_prod(injector: Injector) -> None:
    """Конфигурация для production-режима"""
    injector.register(ILogger, create_file_logger, LifeStyle.Singleton)
    injector.register(
        IDatabase,
        SqlDatabase,
        LifeStyle.Scoped,
        {'connection_string': 'server=prod;database=app', 'logger': '@ILogger'}
    )
    injector.register(
        IEmailService,
        SmtpEmailService,
        LifeStyle.Singleton,
        {'smtp_server': 'smtp.example.com', 'smtp_port': 587, 'logger': '@ILogger'}
    )


def demo(injector: Injector) -> None:
    """Демонстрация работы инжектора"""
    print("\n=== Демонстрация работы инжектора ===")

    try:
        # Получаем экземпляры сервисов
        logger = injector.get_instance(ILogger)
        logger.log("Начало работы приложения")

        # Работа с областью видимости (scope)
        with injector.scope():
            db1 = injector.get_instance(IDatabase)
            db1.connect()
            db1.query("SELECT * FROM users")

            db2 = injector.get_instance(IDatabase)
            print(f"db1 и db2 это один и тот же экземпляр в scope? {db1 is db2}")

        # Вне scope - для Scoped будет создан новый экземпляр
        try:
            db3 = injector.get_instance(IDatabase)
            print(f"db1 и db3 это один и тот же экземпляр? {db1 is db3}")
        except RuntimeError as e:
            print(f"Ошибка при получении экземпляра вне scope: {str(e)}")

        # Singleton всегда возвращает один и тот же экземпляр
        email1 = injector.get_instance(IEmailService)
        email2 = injector.get_instance(IEmailService)
        print(f"email1 и email2 это один и тот же экземпляр? {email1 is email2}")

        email1.send_email("user@example.com", "Test", "Hello World!")

    except Exception as e:
        print(f"Ошибка в демонстрационном примере: {str(e)}")


# Запуск демонстрации
if __name__ == "__main__":
    print("=== Конфигурация разработки ===")
    injector_dev = Injector()
    configure_dev(injector_dev)
    demo(injector_dev)

    print("\n=== Конфигурация production ===")
    injector_prod = Injector()
    configure_prod(injector_prod)
    demo(injector_prod)

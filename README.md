# 🎓 EduAI: Интеллектуальная образовательная экосистема 

![Status](https://img.shields.io/badge/status-in%20development-orange?style=for-the-badge)
![Version](https://img.shields.io/badge/version-0.1.0-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.10+-blue?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)

> **EduAI** — это многокомпонентная система на базе агентов и LLM, разрабатываемая для поддержки образовательного процесса. Система объединяет инструменты для студентов (учебный ассистент, менторство), преподавателей (проверка ДЗ, ассистент, отбор литературы) и автоматизации рутины в единый интерфейс.

---

## 🏗 Архитектура Системы

Проект реализуется по архитектуре **Main Agent + MCP Servers**. Центральная модель-оркестратор распределяет задачи между специализированными модулями (MCP), каждый из которых отвечает за конкретную предметную область.

```mermaid
graph TD
    User((Пользователь)) -->|Telegram / Web| Gateway[API Gateway]
    Gateway --> Agent[🧠 Main Agent / Orchestrator]
    
    subgraph "MCP Servers"
        RAG_Svr[RAG Service]
        HW_Svr[Homework Checker]
        Paper_Svr[PsyArXiv Selector]
        Teach_Svr[Teacher Assistant]
        Mentor_Svr[Student Mentor]
        Voice_Svr[Voice Assistant]
    end
    
    subgraph "External Integrations"
        CloudRAG[(Cloud.ru RAG API)]
        OSF[OSF / PsyArXiv API]
        UniDB[(Внутренняя БД)]
        STT_TTS[Speech-to-Text / TTS]
    end
    
    subgraph "Data & Logging"
        Logs[Structured Logging & Token Tracking]
        VectorDB[(FAISS / Vector DB)]
    end

    Agent -->|Запрос: Учебный материал| RAG_Svr[RAG Service]
    Agent -->|Запрос: Проверка ДЗ| HW_Svr[Homework Checker]
    Agent -->|Запрос: Поиск статей| Paper_Svr[PsyArXiv Selector]
    Agent -->|Запрос: Расписание/Документы| Teach_Svr[Teacher Assistant]
    Agent -->|Запрос: Поддержка студента| Mentor_Svr[Student Mentor]
    Agent -->|Запрос: Голос| Voice_Svr[Voice Assistant]

    Agent --> Logs[Structured Logging & Token Tracking]

    RAG_Svr --> VectorDB[(FAISS / Vector DB)]
    
    RAG_Svr --> CloudRAG[(Cloud.ru RAG API)]

    Paper_Svr --> OSF[OSF / PsyArXiv API]
    Teach_Svr --> UniDB[(Внутренняя БД)]
    Voice_Svr --> STT_TTS[Speech-to-Text / TTS]

```

---
## 🔄 Ключевые Сценарии (Data Flow)

### 1. RAG-помощник в Telegram
Поток обработки запроса студента через облачный RAG.

```mermaid
sequenceDiagram
    participant U as Студент (Telegram)
    participant B as Bot (Python)
    participant C as Cloud.ru IAM
    participant R as Cloud.ru RAG
    participant L as Logger
    
    U->>B: Отправляет вопрос
    B->>C: Запрос токена (KeyID/Secret)
    C-->>B: Access Token
    B->>R: POST /query (Token + Query + Context Settings)
    R-->>B: JSON Response (llm_answer, chunks)
    B->>L: Log: user_id, query_length, response_length, tokens
    alt Ответ < лимита (4096 символов)
        B->>U: Отправка ответа (Markdown + Tables)
    else Ответ > лимита
        B->>U: "Ответ слишком объёмный. Пожалуйста, уточните вопрос."
    end
```

### 2. Модуль первичной проверки ДЗ
Автоматическая валидация перед передачей преподавателю.

```mermaid
graph LR
    Start[Студент загружает файл] --> Check[🔍 MCP: Homework Checker]
    Check -->|Анализ | Format{Формат верен?}
    Format -->|Нет | Feedback[Генерация чек-листа ошибок]
    Feedback --> Reply[Отправка рекомендаций студенту]
    Format -->|Да | Content{Содержание соответствует?}
    Content -->|Нет | Feedback
    Content -->|Да | Notify[✅ Уведомление преподавателю]
    Notify --> End[Задание в очереди на проверку]
    
```

### 3. 📚 PsyArXiv Selector — Сбор и фильтрация статей
Процесс агрегации научных публикаций из открытых источников.

```mermaid
flowchart TB
    Start[🔄 Запуск по расписанию / По запросу] --> Fetch[📡 Запрос к OSF/PsyArXiv API]
    Fetch --> Raw[📄 Получение сырых данных JSON]
    Raw --> Filter1{🔍 Фильтр 1: Дата публикации}
    Filter1 -->|Старше 3х дней| Discard1[❌ Отклонить]
    Filter1 -->|Актуально| Filter2{🔍 Фильтр 2: Ключевые слова}
    Filter1 -->|Актуально| Filter3{🔍 Фильтр 3: семантический поиск}
    
  
    Filter2 -->|Нет совпадений| Discard2[❌ Отклонить]
    Filter3 -->|Нет совпадений| Discard3[❌ Отклонить]
    
    
    Filter2 -->|Совпадения| Filter4{🔍 Фильтр 3: Тип документа}
    Filter3 -->|Совпадения| Filter4{🔍 Фильтр 3: Тип документа}
    Filter4 -->|Не статья| Discard4[❌ Отклонить]
    Filter4 -->|Статья/Препринт| Extract[📝 Извлечение метаданных]
    
    Extract --> Meta[Заголовок, Авторы, DOI, Abstract, PDF Link]
    Meta --> Summary[🤖 LLM Summary Generation]
    Summary --> Store[(💾 Локальное хранилище / Vector DB)]
    Store --> Index[📑 Индексация для поиска]
    Index --> Ready[✅ Доступно через MCP для Main Agent]
    

```

### 4. 👨‍🏫 Teacher Assistant — Помощник преподавателя
Работа с расписанием, документами и уведомлениями.

```mermaid
sequenceDiagram
    participant T as Преподаватель
    participant Bot as Telegram Bot
    participant TA as Teacher Assistant MCP
    participant UniDB[(Внутренняя БД)]
    participant Notify[Система Уведомлений]
    participant Docs[Репозиторий Документов]
    
    T->>Bot: Команда: /schedule
    Bot->>TA: Запрос расписания
    TA->>UniDB: SQL Query (group_id, date_range)
    UniDB-->>TA: Данные расписания
    TA-->>Bot: Форматированный ответ
    Bot-->>T: 📅 Расписание (таблица)
    
    T->>Bot: Команда: /notify students
    Bot->>TA: Создание уведомления
    TA->>UniDB: Получение списка студентов группы
    UniDB-->>TA: Список student_id + contacts
    TA->>Notify: Отправка сообщений
    Notify-->>Bot: Статус доставки
    Bot-->>T: ✅ Отправлено: 25/25
    
    T->>Bot: Запрос документа
    Bot->>TA: Поиск по названию
    TA->>Docs: File Search (метаданные)
    Docs-->>TA: Ссылка на файл
    TA-->>Bot: Документ + превью
    Bot-->>T: 📄 Файл для скачивания
    
    note right of TA: Все действия логируются<br/>для аудита
```

### 5. 🧠 Общая архитектура взаимодействия MCP-серверов
Как модули коммуницируют через Main Agent.

```mermaid
graph TB
    subgraph "User interfaces"
        TG[Telegram Bot]
        WEB[Web Interface]
        VOICE[Голосовой интерфейс]
    end
    
    subgraph "Оркестрация"
        MA[🧠 Main Agent]
        Router{Маршрутизатор запросов}
        Context[Контекст диалога]
    end
    
    subgraph "MCP Серверы"
        RAG[RAG Service]
        HW[Homework Checker]
        PSY[PsyArXiv Selector]
        TA[Teacher Assistant]
        MENT[Student Mentor]
    end
    
    subgraph "Внешние сервисы"
        CLOUD[Cloud.ru RAG]
        OSF[OSF/PsyArXiv]
        UNIDB[Вузовская БД*]
        VECTOR[Vector DB]
    end
    
    TG --> MA
    WEB --> MA
    VOICE --> MA
    
    MA --> Router
    Router --> Context
    Context --> RAG
    Context --> HW
    Context --> PSY
    Context --> TA
    Context --> MENT
    
    RAG --> CLOUD
    RAG --> VECTOR
    PSY --> OSF
    TA --> UNIDB
    

```


---

## 🧩 Модули Проекта

| Модуль | Описание | Путь | Статус |
| :--- | :--- | :--- | :--- |
| **🤖 Core Agent** | Оркестратор: маршрутизация запросов, управление контекстом, логирование | [`/src/core`](./src/core) | 🚧 В разработке |
| **📚 RAG Service** | Интеграция с Cloud.ru RAG, обработка Markdown/таблиц, лимиты токенов | [`/src/modules/rag`](./src/modules/rag) | 🚧 В разработке |
| **📝 Homework Checker** | Предварительная проверка ДЗ: оформление, объем, ключевые слова | [`/src/modules/homework`](./src/modules/homework) | 🚧 В разработке |
| **🔍 PsyArXiv Selector** | Скрипты сбора статей (OSF), фильтрация по регулярным выражениям, саммари | [`/src/modules/papers`](./src/modules/papers) | 🟡 MVP готов |
| **👨‍🏫 Teacher Assistant** | Работа с расписанием, уведомления, доступ к внутренней документации вуза | [`/src/modules/teacher`](./src/modules/teacher) | 🚧 В разработке |
| **🗣️ Voice Assistant** | STT/TTS обвязка для голосового взаимодействия на занятиях | [`/src/modules/voice`](./src/modules/voice) | 📅 Planned |
| **🎓 Student Mentor** | Долгосрочное сопровождение, трекинг прогресса, адаптивные подсказки | [`/src/modules/mentor`](./src/modules/mentor) | 📅 Planned |
| **🔌 MCP Protocol** | Базовая реализация протокола взаимодействия агента и инструментов | [`/src/mcp`](./src/mcp) | 🚧 В разработке |

> **Легенда:** 🚧 В разработке | 🟡 MVP / Прототип | ✅ Готово | 📅 Запланировано

---




## 📊 Детальное описание новых модулей

### 🔍 PsyArXiv Selector

**Назначение:** Автоматический сбор, фильтрация и суммаризация научных публикаций по психологии из открытых репозиториев.

**Ключевые функции:**
| Функция | Описание |
| :--- | :--- |
| **API Integration** | Запросы к OSF/PsyArXiv API с пагинацией |
| **Regex Filtering** | Фильтрация по ключевым словам (психология, когнитивный, терапия...) |
| **Date Filtering** | Отбор публикаций за последний год |
| **LLM Summary** | Генерация краткого содержания (abstract + key findings) |
| **Indexing** | Сохранение метаданных для быстрого поиска через RAG |

**Выходные данные:**
```json
{
  "paper_id": "osf-xxxxx",
  "title": "Название статьи",
  "authors": ["Автор 1", "Автор 2"],
  "published_date": "2026-01-15",
  "doi": "10.xxxx/xxxxx",
  "pdf_url": "https://...",
  "summary_ru": "Краткое содержание на русском",
  "keywords": ["психология", "когнитивный"],
  "indexed_at": "2026-01-20T10:00:00Z"
}
```

---

### 👨‍🏫 Teacher Assistant

**Назначение:** Автоматизация рутинных задач преподавателя: расписание, уведомления, доступ к документам.

**Ключевые функции:**
| Функция | Описание |
| :--- | :--- |
| **Schedule Query** | Получение расписания из внутренней БД вуза |
| **Bulk Notifications** | Массовая рассылка уведомлений студентам группы |
| **Document Search** | Поиск методичек, шаблонов, приказов по репозиторию |
| **Audit Logging** | Логирование всех действий для отчётности |
| **Group Management** | Работа со списками групп и студентов |

**Примеры команд в Telegram:**
```
/schedule [группа] [дата]     — Показать расписание
/notify [группа] [текст]      — Отправить уведомление
/doc [название]               — Найти документ
/students [группа]            — Список студентов
```

## 🛠 Технологический Стек

*   **Язык:** Python 3.10+
*   **LLM & RAG:** Cloud.ru Managed RAG, GigaChat / OpenAI API, LangChain
*   **Bot Framework:** `python-telegram-bot` (v20+), `asyncio`
*   **Data Processing:** Pandas, Regex, FAISS (локально для прототипов)
*   **Infrastructure:** Docker, `.env` configuration, Structured Logging
*   **Tracking:** Comet.ml (эксперименты), File-based logs (диалоги)

---



## 📄 Лицензия

MIT License.   

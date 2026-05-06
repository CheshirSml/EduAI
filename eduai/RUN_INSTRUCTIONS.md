# 🚀 Инструкция по запуску EduAI Local (v0.3.0-local)

## 📋 Предварительные требования

### Аппаратные требования
- ОС: Windows 10 / Linux
- RAM: 16 ГБ минимум
- GPU: NVIDIA RTX 3050 8 ГБ (опционально, работает и на CPU)
- Свободное место: ~10 ГБ (для модели и данных)

### Программные требования
- Python >= 3.10
- llama.cpp (собранный бинарник `main`)

---

## 🔧 Шаг 1: Установка зависимостей

```bash
cd eduai

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements-local.txt
```

---

## 🔧 Шаг 2: Установка llama.cpp

### Вариант A: Сборка из исходников (рекомендуется)

```bash
# Клонирование репозитория
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# Сборка с поддержкой CUDA (для NVIDIA GPU)
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release

# Проверка
./build/bin/main --help
```

### Вариант B: Готовые бинарники

Скачайте готовые бинарники с [GitHub Releases](https://github.com/ggerganov/llama.cpp/releases).

---

## 🔧 Шаг 3: Скачивание модели

```bash
# Создайте директорию для моделей
mkdir -p data/models

# Скачайте модель Qwen3.5-4B-Q4_K_M.gguf (~2.7 ГБ)
# Например, через huggingface-cli:
pip install huggingface-hub
huggingface-cli download Qwen/Qwen3.5-4B-Instruct-GGUF Qwen3.5-4B-Q4_K_M.gguf --local-dir data/models

# Или вручную поместите файл модели в data/models/
```

---

## 🔧 Шаг 4: Настройка конфигурации

```bash
# Скопируйте пример .env
cp .env.example .env

# Отредактируйте .env при необходимости:
# - DEFAULT_MODEL: имя вашей GGUF модели
# - LLAMA_CPP_PATH: путь к бинарнику llama.cpp main
# - GPU_LAYERS: 35 для RTX 3050, 0 для CPU-only
```

---

## 🔧 Шаг 5: Создание тестовых данных

Структура папок уже создана в `data/`:
```
data/
├── specs/
│   └── psychology_stress/
│       ├── assignment_spec.md    # Спецификация задания
│       └── grading_rubric.json   # Рубрика оценки
├── assignments/                   # Папка для работ студентов
│   └── ПСи-201/
│       └── Иванов И.И./
│           └── essay.txt
├── models/                        # GGUF модели
├── logs/                          # Логи
└── cache/                         # Кэш обработанных файлов
```

Для создания тестовой работы студента:

```bash
mkdir -p data/assignments/ПСи-201/"Иванов И.И."

cat > "data/assignments/ПСи-201/Иванов И.И./essay.txt" << 'EOF'
Введение

Стресс является важной проблемой современного общества...

Основная часть

Согласно исследованиям (Петров, 2020), стресс влияет на...

Выводы

Таким образом, эффективные копинг-стратегии важны...

Список литературы

1. Петров А.А. (2020). Психология стресса. М.: Наука.

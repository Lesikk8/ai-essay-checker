# AI Essay Checker

PoC-проєкт з курсу «Хмарні обчислення» (завдання 2): вебзастосунок, який перевіряє есе англійською мовою за допомогою **Gemini API** і розгортається в **Google Cloud Run**.

Автор: Певна Олеся, ТК-41

## Що вміє

- знаходить граматичні, лексичні та стильові помилки і підсвічує їх у тексті;
- пояснює кожне правило українською мовою;
- оцінює есе за 4 критеріями (граматика, лексика, зв’язність, виконання завдання; 0–5 кожен);
- визначає рівень CEFR (A1–C2);
- зберігає звіти у **Firestore** і показує прогрес студента.

## Архітектура

```
Браузер → Flask (Cloud Run) → Gemini API (JSON за схемою) → Firestore
                  ↑
         Secret Manager (GEMINI_API_KEY)
```

| Сервіс | Роль |
| --- | --- |
| Gemini API | аналіз есе, structured output за Pydantic-схемою `EssayReport` |
| Cloud Run | запуск контейнера з Flask, масштабування до нуля |
| Cloud Build / Artifact Registry | збирання та зберігання Docker-образу |
| Firestore | звіти та історія перевірок |
| Secret Manager | зберігання ключа Gemini API поза кодом |

## Структура

```
app.py               маршрути Flask, перевірка довжини, підсвічування помилок
checker/llm.py       запит до Gemini, схема відповіді, запасні моделі, захист від галюцинацій
checker/storage.py   збереження й читання історії у Firestore
templates/, static/  інтерфейс
samples/             приклад есе для демонстрації
Dockerfile           образ для Cloud Run
```

## Локальний запуск (macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="ваш_ключ"
export USE_FIRESTORE=0
python app.py
```

Відкрити http://localhost:8080

## Розгортання в Google Cloud Run

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com firestore.googleapis.com secretmanager.googleapis.com

gcloud firestore databases create --location=europe-central2

printf "ваш_ключ" | gcloud secrets create gemini-api-key --data-file=-

gcloud run deploy ai-essay-checker \
    --source . --region europe-central2 \
    --allow-unauthenticated \
    --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
    --memory 512Mi --max-instances 1
```

Сервісному акаунту Cloud Run потрібні ролі `Secret Manager Secret Accessor` і `Cloud Datastore User`.

## Змінні середовища

| Змінна | Значення |
| --- | --- |
| `GEMINI_API_KEY` | ключ з Google AI Studio |
| `GEMINI_MODELS` | список моделей через кому (за замовчуванням `gemini-3.8-flash,gemini-3.5-flash,gemini-3.5-flash-lite`) |
| `USE_FIRESTORE` | `1` — зберігати історію (за замовчуванням), `0` — вимкнути |

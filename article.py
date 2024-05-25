import os
import time
import re
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, Any
import google.generativeai as genai
from google.api_core import exceptions, retry

# Load environment variables from .env file
load_dotenv()

# Configure the API key from the environment variable
GOOGLE_API_KEY = "GOOGLE_API_KEY_GOES_HERE"
if not GOOGLE_API_KEY:
    raise ValueError("API key not found. Ensure that the .env file contains the 'GOOGLE_API_KEY' variable.")
genai.configure(api_key=GOOGLE_API_KEY)

# Define the models with descriptions
MODELS: Dict[str, Dict[str, Any]] = {
    "gemini-1.5-flash-latest": {
        "model": genai.GenerativeModel("gemini-1.5-flash-latest"),
        "description": "Powerful model capable of handling text and image inputs, optimized for various language tasks like code generation, text editing, and problem solving.",
        "rate_limit": (15, 60),  # 2 queries per minute
        "daily_limit": 1000,
    },
    "gemini-1.0-pro-latest": {
        "model": genai.GenerativeModel("gemini-1.0-pro-latest"),
        "description": "Versatile model for text generation and multi-turn conversations, suitable for zero-shot, one-shot, and few-shot tasks.",
        "rate_limit": (60, 60),  # 60 queries per minute
    },
    "gemini-1.5-pro-latest": {
        "model": genai.GenerativeModel("gemini-1.5-pro-latest"),
        "description": "Versatile model for text generation and multi-turn conversations, suitable for zero-shot, one-shot, and few-shot tasks.",
        "rate_limit": (2, 60),  # 60 queries per minute
    },
}

@retry.Retry(
    initial=0.1,
    maximum=60.0,
    multiplier=2.0,
    deadline=600.0,
    exceptions=(exceptions.GoogleAPICallError,),
)
def generate_with_retry(model: genai.GenerativeModel, prompt: str) -> Any:
    try:
        return model.generate_content(prompt)
    except exceptions.InvalidArgument as e:
        raise ValueError(f"Invalid input provided: {e}")
    except exceptions.DeadlineExceeded as e:
        raise exceptions.DeadlineExceeded(f"Deadline exceeded while generating content: {e}")
    except exceptions.ResourceExhausted as e:
        raise exceptions.ResourceExhausted(f"Resource exhausted (quota limit reached): {e}")

def sanitize_title(title: str) -> str:
    sanitized_title = re.sub(r"[^\w\-_\. ]", "_", title)
    return sanitized_title[:100]

def extract_text(response: Any) -> str:
    for part in response.parts:
        if hasattr(part, "text"):
            return part.text
    return ""

def create_article_directory() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    article_dir = f"article_{timestamp}"
    os.makedirs(article_dir, exist_ok=True)
    return article_dir

def generate_article_prompt(draft: str, section: str, add_copy: bool = False) -> str:
    copy_instructions = (
        " Also, generate the necessary textual content for this section." if add_copy else ""
    )
    return (
        f"Generate the next part of an extensive article using the following instructions:{copy_instructions} "
        f"Here is the text generated so far:\n\n"
        f"{draft}\n\n"
        f"Now generate the text for the following section:\n\n"
        f"{section}\n"
    )

def ask_user_for_article_topic() -> str:
    article_topic = input("Enter the topic of the article you want to write: ").strip()
    return article_topic

def generate_article_guide(model: genai.GenerativeModel, article_topic: str) -> str:
    prompt = (
        f"Generate a detailed step-by-step guide or outline on how to write an extensive article about '{article_topic}'. "
        f"Include the necessary sections, and explain what should be covered in each section."
    )
    response = generate_with_retry(model, prompt)
    return extract_text(response)

def write_article(model_name: str, article_topic: str, article_guide: str) -> None:
    model_config = MODELS[model_name]
    model = model_config["model"]
    rate_limit = model_config.get("rate_limit")
    daily_limit = model_config.get("daily_limit")

    # Extract article sections from the guide
    article_sections = article_guide.split("\n\n")
    
    # Create a directory for the article
    article_dir = create_article_directory()

    draft = ""
    query_count = 0
    max_iterations = 150

    for i, section in enumerate(article_sections):
        print(f"Generating section {i + 1} out of {len(article_sections)}...")
        if query_count >= max_iterations:
            break

        # Generate text for each section
        article_prompt = generate_article_prompt(draft, section, add_copy=True)
        continuation = extract_text(generate_with_retry(model, article_prompt))
        draft += "\n\n" + continuation

        # Save each section's text
        section_filename = f"{article_dir}/section_{i + 1}.txt"
        with open(section_filename, "w", encoding="utf-8") as file:
            file.write(continuation)

        query_count += 1

        if rate_limit and query_count % rate_limit[0] == 0:
            time.sleep(rate_limit[1])

        if daily_limit and query_count >= daily_limit:
            print("Daily query limit reached. Please try again tomorrow.")
            break

    # Save the final article
    final_article = draft.strip()
    final_filename = f"{article_dir}/{sanitize_title(article_topic)}.txt"
    with open(final_filename, "w", encoding="utf-8") as file:
        file.write(final_article)

    print("Final Article:")
    print(final_article)

def select_model() -> str:
    print("Available models:")
    for i, (model_name, model_info) in enumerate(MODELS.items(), start=1):
        print(f"{i}. {model_name} - {model_info['description']}")

    while True:
        try:
            choice = int(input("Enter the number corresponding to the model you want to use: "))
            if 1 <= choice <= len(MODELS):
                return list(MODELS.keys())[choice - 1]
            else:
                print("Invalid choice. Please enter a valid number.")
        except ValueError:
            print("Invalid input. Please enter a valid number.")

if __name__ == "__main__":
    selected_model = select_model()
    article_topic = ask_user_for_article_topic()
    article_guide = generate_article_guide(MODELS[selected_model]["model"], article_topic)
    print(f"Generated guide for writing an article on '{article_topic}':\n{article_guide}")
    write_article(selected_model, article_topic, article_guide)

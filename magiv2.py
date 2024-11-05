import os
import re
import json
import shutil
import numpy as np
from pathlib import Path
from PIL import Image
import torch
import argparse

from PIL import Image
import numpy as np
from transformers import AutoModel
import torch

def create_save_folder(folder_path):
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
    os.makedirs(folder_path, exist_ok=True)

def create_chapter_pages_and_character_bank(image, character):
    # Create lists for chapter pages and character bank
    chapter_pages = []
    character_bank = {
        "images": [],
        "names": []
    }

    # Iterate through manga images to create chapter_pages
    for image_file in os.listdir(image):
        if image_file.endswith(('.png', '.jpg', '.jpeg')):  # Check for image file extensions
            # Extract the page number using regex
            match = re.search(r'p(\d+)', image_file)
            if match:
                page_number = int(match.group(1))  # Convert to integer for sorting
                chapter_pages.append((page_number, image_file))  # Store as tuple (page_number, image_file)
            else:
                page_number = image_file.rsplit(".", 1)[0]
                chapter_pages.append((page_number, image_file))  # Store as tuple (page_number, image_file)

    # Sort chapter pages by page number
    chapter_pages.sort(key=lambda x: x[0])
    chapter_pages = [os.path.join(image, img[1]) for img in chapter_pages]  # Extract just the filenames after sorting

    # Iterate through character images to create character bank
    for char_image_file in os.listdir(character):
        if char_image_file.endswith(('.png', '.jpg', '.jpeg')):  # Check for image file extensions
            # Split the filename to extract character name
            char_name = char_image_file.split('_')[0]  # Get the part before the underscore
            character_bank["images"].append(os.path.join(character, char_image_file))
            character_bank["names"].append(char_name)

    return chapter_pages, character_bank


def read_image(path_to_image):
    with open(path_to_image, "rb") as file:
        image = Image.open(file).convert("L").convert("RGB")
        image = np.array(image)
    return image


def process_manga_and_characters(image_path, character_folder_path, model, json_output_dir, transcript_output_dir):
    # Define your folders
    image = Path(image_path)
    character = Path(character_folder_path)

    # Get chapter pages and character bank
    chapter_pages_original, character_bank_original = create_chapter_pages_and_character_bank(image, character)

    # Read images for chapter pages and character bank
    chapter_pages = [read_image(x) for x in chapter_pages_original]
    character_bank = character_bank_original.copy()
    character_bank["images"] = [read_image(x) for x in character_bank_original["images"]]

    # Assuming 'model' is defined elsewhere
    with torch.no_grad():
        per_page_results = model.do_chapter_wide_prediction(chapter_pages, character_bank, use_tqdm=True, do_ocr=True)

    # Prepare directories for saving results
    create_save_folder(json_output_dir)  
    create_save_folder(transcript_output_dir)  

    # Process and save the results
    transcript = []
    for i, (image, page_result) in enumerate(zip(chapter_pages, per_page_results)):
        image_name_ext = os.path.basename(chapter_pages_original[i]) 
        # Split the image name and its extension
        image_name, _ = os.path.splitext(image_name_ext)
        
        # Save page_result to JSON
        json_file_path = os.path.join(json_output_dir, f"{image_name}.json")
        with open(json_file_path, 'w') as json_file:
            json.dump(page_result, json_file, indent=4)

        speaker_name = {
            text_idx: page_result["character_names"][char_idx] for text_idx, char_idx in page_result["text_character_associations"]
        }
        
        transcript.append(f"<page>{image_name}<endpage>")
        for j in range(len(page_result["ocr"])):
            if not page_result["is_essential_text"][j]:
                continue
            name = speaker_name.get(j, "unsure") 
            transcript.append(f"<name>{name}<endname>: {page_result['ocr'][j]}")

    # Save the transcript to a text file
    transcript_file_path = os.path.join(transcript_output_dir, "transcript.txt")
    with open(transcript_file_path, "w") as fh:
        for line in transcript:
            fh.write(line + "\n")

    print("\n\nDone you WEEEEB!")


def parse_args():
    parser = argparse.ArgumentParser(description="Process manga and character images and generate results.")
    parser.add_argument("-i", "--image", default="input/raw", type=str, help="Path to the folder containing manga images (raw manga).")
    parser.add_argument("-c", "--character", default="input/character",type=str, help="Path to the folder containing character images.")
    parser.add_argument("-j", "--json", default="json", type=str, help="Directory where the JSON results will be saved.")
    parser.add_argument("-t", "--transcript", default="transcript", type=str, help="Directory where the transcript text file will be saved.")
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command-line arguments
    args = parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Running on {device}")
    magiv2_model = AutoModel.from_pretrained("ragavsachdeva/magiv2", trust_remote_code=True).to(device).eval()

    process_manga_and_characters(args.image, args.character, magiv2_model, args.json, args.transcript)

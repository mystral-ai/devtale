CODE_EXTRACTOR_TEMPLATE = """
Given the provided code snippet enclosed within the <<< >>> delimiters, your \
task is to output the classes and method names that are defined within the code. \
You must not include classes that are imported.
Additionally, you should include a concise top-level docstring that summarizes \
the purpose of the code snippet.

Your output must adhere to the following format:
classes=["class_name_1", "class_name_2", ...]
methods=["method_name_1", "method_name_2", ...]
summary="top-level docstring"

Code: <<< {code} >>>
"""

CODE_LEVEL_TEMPLATE = """
Your objective is to generate Google Style docstrings for code elements provided \
in the input.
The input consists of two parts:

1. A code snippet enclosed within the <<< >>> delimiters.
2. A list of code elements (classes and/or methods): "{code_elements}".

Your task involves the following steps:

1. Analyze the provided code snippet to locate and identify the methods and/or \
classes that are actually defined within the code snippet, based on the list of  \
code elements.
2. For each identified code element, generate a Google Style docstring.

Focus only on the code elements that are present and defined within the code snippet.
And please refrain from including docstrings within the code.

{format_instructions}

Do not introduce your answer, just output using the above JSON schema, and always \
use escaped newlines.

Input: <<< {code} >>>
"""

UNKNOWN_FILE_LEVEL_TEMPLATE = """
Using the following code enclosed within the <<< >>> delimeters write a top-file level \
docstring for a concise summary that effectively captures the overall purpose and \
functionality of the code.

code: <<< {information} >>>

Ensure your final summary is no longer than three sentences.
"""

FILE_LEVEL_TEMPLATE = """
The following summaries enclosed within the <<< >>> delimeters are derived from the \
same code file. Write a top-file level docstring that combines them into a concise  \
final summary that effectively captures the overall purpose and functionality of the \
entire code file.

Summaries: <<< {information} >>>

Ensure your final summary is no longer than three sentences.
"""

FOLDER_LEVEL_TEMPLATE = """
Generate a markdown text using the enclosed \
information within the <<< >>> delimiters as your context. \
Your output must strictly adhere to the provided structure below \
without adding any other section more than the folder name on it.

This is the structure your markdown text must have:
Structure:
----------
#### <<<folder_name>>>

<<<folder_overview>>> (Paragraph that concisely communicates the \
folder's purpose.

- *<<<file_name>>>*: <<<file_description>>> (Your task it to
write a short description of what the file does.)
----------

Folder information: <<< {information} >>>

Ensure proper formatting and adhere to Markdown syntax guidelines, \
and always use escaped newlines.
Do not add sections that are not listed in the provided structure.

Output your answer as a JSON with the keys: folder_overview and folder_readme.

folder_readme is the markdown text, and folder_overview is a brief description \
of the folder context.
"""


ROOT_LEVEL_TEMPLATE = """
Generate a markdown text using the enclosed \
information within the <<< >>> delimiters as your context. \
Your output must strictly adhere to the provided structure below \
without adding any other section not mentioned on it.

This is the structure your output must have:
Structure:
----------
# <<<repository_name>>> (Please ensure that the initial letter \
is capitalized)

## Description
(Provide a concise one-line sentence that describes the primary \
purpose of the code, utilizing all the contextual details \
available.)

## Overview
(In this section, your task is to create a single, well-structured \
paragraph that concisely communicates the reasons behind the \
repository's creation, its objectives, and the mechanics underlying \
its functionality.)
----------

Repository information: <<< {information} >>>

Ensure proper formatting and adhere to Markdown syntax guidelines.
Do not add sections that are not listed in the provided structure.
"""

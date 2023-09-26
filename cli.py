import copy
import getpass
import json
import logging
import os

import click
from dotenv import load_dotenv

from devtale.aggregators import (
    GoAggregator,
    JavascriptAggregator,
    PHPAggregator,
    PythonAggregator,
)
from devtale.constants import (
    ALLOWED_EXTENSIONS,
    ALLOWED_NO_CODE_EXTENSIONS,
    DOCSTRING_LABEL,
    LANGUAGES,
)
from devtale.utils import (
    build_project_tree,
    extract_code_elements,
    fuse_tales,
    get_unit_tale,
    prepare_code_elements,
    redact_tale_information,
    split_code,
    split_text,
)

DEFAULT_OUTPUT_PATH = "devtale_demo/"
DEFAULT_MODEL_NAME = "gpt-4"


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_repository(
    root_path: str,
    output_path: str = DEFAULT_OUTPUT_PATH,
    model_name: str = DEFAULT_MODEL_NAME,
    fuse: bool = False,
    debug: bool = False,
    cost_estimation: bool = True,
) -> None:
    cost = 0
    folder_tales = {
        "repository_name": os.path.basename(os.path.abspath(root_path)),
        "folders": [],
    }

    # get original readme before creating a new one
    original_readme_content = None
    for file_name in ["readme.md", "README.md"]:
        readme_path = os.path.join(root_path, file_name)
        if os.path.exists(readme_path):
            with open(readme_path, "r") as file:
                original_readme_content = file.readlines()
            if root_path == output_path:
                try:
                    os.rename(readme_path, os.path.join(root_path, "old_readme.md"))
                except OSError as e:
                    logger.info(f"Error keeping the original readme file: {e}")
            break

    # get project structure before we modify it
    gitignore_path = os.path.join(root_path, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as gitignore_file:
            gitignore_patterns = [
                line.strip() for line in gitignore_file if line.strip()
            ]
    else:
        gitignore_patterns = None

    project_tree, file_paths = build_project_tree(
        root_path, gitignore_patterns=gitignore_patterns
    )
    project_tree = ".\n" + project_tree

    folders = list(set([os.path.dirname(file_path) for file_path in file_paths]))
    folders = sorted(folders, key=lambda path: path.count("/"))

    folders_readmes = []
    for folder_path in folders:
        try:
            if not folder_path.endswith("/"):
                folder_path += "/"

            folder_full_name = os.path.relpath(folder_path, root_path)

            folder_readme, folder_tale, folder_cost = process_folder(
                folder_path=folder_path,
                output_path=os.path.join(output_path, folder_full_name)
                if folder_full_name != "."
                else output_path,
                model_name=model_name,
                fuse=fuse,
                debug=debug,
                folder_full_name=folder_full_name,
                cost_estimation=cost_estimation,
            )
            cost += folder_cost

        except Exception as e:
            folder_name = os.path.basename(folder_path)
            logger.info(
                f"Failed to create folder-level tale for {folder_name} - Exception: {e}"
            )
            folder_tale = None

        if folder_tale:
            folders_readmes.append("\n\n" + folder_readme)
            # add root folder summary information
            if folder_path == folders[0]:
                folder_tales["folders"].append(
                    {
                        "folder_name": os.path.basename(os.path.abspath(root_path)),
                        "folder_summary": folder_tale,
                        "is_the_root_folder": True,
                    }
                )
            else:
                folder_tales["folders"].append(
                    {
                        "folder_name": folder_full_name,
                        "folder_summary": folder_tale,
                    }
                )

    if debug:
        logger.debug(f"FOLDER_TALES: {folder_tales}")
        return None

    if folder_tales:
        folder_summaries = split_text(str(folder_tales), chunk_size=15000)
        root_readme, call_cost = redact_tale_information(
            "root-level",
            folder_summaries,
            model_name="gpt-3.5-turbo-16k",
            cost_estimation=cost_estimation,
        )
        cost += call_cost
        root_readme = root_readme.replace("----------", "")

        # inject folders information
        if folders_readmes:
            folders_information = "\n\n## Folders" + "".join(folders_readmes)
            root_readme = root_readme + folders_information

        # inject project tree
        tree = f"\n\n## Project Tree\n```bash\n{project_tree}```\n\n"
        root_readme = root_readme + tree

        # inject original readme if there is one
        if original_readme_content:
            filtered_original_readme = [
                line for line in original_readme_content if not line.startswith("# ")
            ]
            modified_original_readme = "\n\n## Extra notes\n\n" + "".join(
                filtered_original_readme
            )

            root_readme = root_readme + modified_original_readme

        if not cost_estimation:
            logger.info("save root json..")
            with open(os.path.join(output_path, "root_level.json"), "w") as json_file:
                json.dump(folder_tales, json_file, indent=2)

            logger.info(f"saving root index in {output_path}")
            with open(
                os.path.join(output_path, "README.md"), "w", encoding="utf-8"
            ) as file:
                file.write(root_readme)

    return cost


def process_folder(
    folder_path: str,
    output_path: str = DEFAULT_OUTPUT_PATH,
    model_name: str = DEFAULT_MODEL_NAME,
    fuse: bool = False,
    debug: bool = False,
    folder_full_name: str = None,
    cost_estimation: bool = False,
) -> None:
    cost = 0
    save_path = os.path.join(output_path, os.path.basename(folder_path))
    tales = []

    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)

        if os.path.isfile(file_path) and (
            os.path.splitext(file_name)[1] in ALLOWED_EXTENSIONS
            or os.path.splitext(file_name)[1] in ALLOWED_NO_CODE_EXTENSIONS
        ):
            logger.info(f"processing {file_path}")
            try:
                file_tale, file_cost = process_file(
                    file_path, save_path, model_name, fuse, debug, cost_estimation
                )
                cost += file_cost
            except Exception as e:
                logger.info(
                    f"Failed to create dev tale for {file_path} - Exception: {e}"
                )
                file_tale = None

            if file_tale is not None:
                if file_tale["file_docstring"]:
                    if not folder_full_name:
                        folder_full_name = os.path.basename(
                            os.path.abspath(folder_path)
                        )

                    if folder_full_name == ".":
                        folder_full_name = "./"

                    folder_entry = next(
                        (
                            item
                            for item in tales
                            if item["folder_name"] == folder_full_name
                        ),
                        None,
                    )
                    if folder_entry is None:
                        folder_entry = {
                            "folder_name": folder_full_name,
                            "folder_files": [],
                        }
                        if folder_full_name == ".":
                            folder_entry[
                                "folder_description"
                            ] = """
                            This is the root path of the repository. The top-level
                            directory.
                            """

                        tales.append(folder_entry)

                    folder_entry["folder_files"].append(
                        {
                            "file_name": file_name,
                            "file_description": file_tale["file_docstring"],
                        }
                    )

    if debug:
        logger.debug(
            f"""FOLDER INFO:
        folder_path: {folder_path}
        output_path: {output_path}
        save_path: {save_path}
        """
        )
        logger.debug(f"FILE_TALES: {tales}")
        return "-", "-", cost

    if tales:
        files_summaries = split_text(str(tales), chunk_size=10000)
        # split into two calls to avoid issues with json decoding markdow text.
        folder_readme, fl_cost = redact_tale_information(
            "folder-level",
            files_summaries,
            model_name="gpt-3.5-turbo-16k",
            cost_estimation=cost_estimation,
        )
        folder_readme = folder_readme.replace("----------", "")

        folder_overview, fd_cost = redact_tale_information(
            "folder-description",
            folder_readme,
            model_name="gpt-3.5-turbo-16k",
            cost_estimation=cost_estimation,
        )

        cost += fl_cost + fd_cost

        if not cost_estimation:
            logger.info("save folder json..")
            with open(os.path.join(save_path, "folder_level.json"), "w") as json_file:
                json.dump(tales, json_file, indent=2)

            logger.info(f"saving index in {save_path}")
            with open(
                os.path.join(save_path, "README.md"), "w", encoding="utf-8"
            ) as file:
                file.write(folder_readme)

        return folder_readme, folder_overview, cost
    return None, None, cost


def process_file(
    file_path: str,
    output_path: str = DEFAULT_OUTPUT_PATH,
    model_name: str = DEFAULT_MODEL_NAME,
    fuse: bool = False,
    debug: bool = False,
    cost_estimation: bool = False,
) -> None:
    cost = 0
    file_name = os.path.basename(file_path)
    file_ext = os.path.splitext(file_name)[-1]
    save_path = os.path.join(output_path, f"{file_name}.json")

    if debug:
        logger.debug(f"FILE INFO:\nfile_path: {file_path}\nsave_path: {save_path}")
        return {"file_docstring": "-"}, cost

    if not os.path.exists(output_path) and not cost_estimation:
        os.makedirs(output_path)

    logger.info("read dev draft")
    with open(file_path, "r") as file:
        code = file.read()

    if not code:
        return {"file_docstring": ""}, cost

    if os.path.exists(save_path):
        logger.info(f"Skipping {file_name} as its tale file already exists.")
        with open(save_path, "r") as file:
            found_tale = json.load(file)
        if fuse:
            fuse_documentation(code, found_tale, output_path, file_name, file_ext)
        return found_tale, cost

    if not file_ext or file_ext in ALLOWED_NO_CODE_EXTENSIONS:
        # a small single chunk is enough
        no_code_file = split_text(code, chunk_size=5000)[0].page_content
        no_code_file_data = {
            "file_name": file_name,
            "file_content": no_code_file,
        }
        file_docstring, call_cost = redact_tale_information(
            content_type="no-code-file",
            docs=no_code_file_data,
            model_name="text-davinci-003",
            cost_estimation=cost_estimation,
        )
        cost += call_cost

        return {"file_docstring": file_docstring}, cost

    logger.info("split dev draft ideas")
    big_docs = split_code(code, language=LANGUAGES[file_ext], chunk_size=10000)
    short_docs = split_code(code, language=LANGUAGES[file_ext], chunk_size=3000)

    logger.info("extract code elements")
    code_elements = []
    for idx, doc in enumerate(big_docs):
        elements_set, call_cost = extract_code_elements(
            big_doc=doc, model_name=model_name, cost_estimation=cost_estimation
        )
        cost += call_cost
        if elements_set:
            code_elements.append(elements_set)

    logger.info("prepare code elements")
    code_elements_dict = prepare_code_elements(code_elements)

    # Make a copy to keep the original dict intact
    code_elements_copy = copy.deepcopy(code_elements_dict)

    # clean
    code_elements_copy.pop("summary", None)
    if not code_elements_copy["classes"]:
        code_elements_copy.pop("classes", None)
    if not code_elements_copy["methods"]:
        code_elements_copy.pop("methods", None)

    logger.info("create tale sections")
    tales_list = []
    # process only if we have elements to document
    if code_elements_copy or cost_estimation:
        for idx, doc in enumerate(short_docs):
            tale, call_cost = get_unit_tale(
                short_doc=doc,
                code_elements=code_elements_copy,
                model_name=model_name,
                cost_estimation=cost_estimation,
            )
            cost += call_cost
            tales_list.append(tale)
            logger.info(f"tale section {str(idx+1)}/{len(short_docs)} done.")

    logger.info("create dev tale")
    tale, errors = fuse_tales(tales_list, code, code_elements_dict)

    if len(errors) > 0:
        logger.info(
            f"We encountered errors while fusing the following \
                    tales for {file_name} - Corrupted tales: {errors}"
        )

    logger.info("add dev tale summary")
    summaries = split_text(str(code_elements_dict["summary"]), chunk_size=9000)

    file_docstring, call_cost = redact_tale_information(
        content_type="top-level",
        docs=summaries,
        model_name="text-davinci-003",
        cost_estimation=cost_estimation,
    )
    cost += call_cost

    if fuse and not cost_estimation:
        # add docstring label only to insert it along the docstring into the code
        tale["file_docstring"] = DOCSTRING_LABEL + "\n" + file_docstring
        fuse_documentation(code, tale, output_path, file_name, file_ext)

    tale["file_docstring"] = file_docstring

    logger.info(f"save dev tale in: {save_path}")

    if not cost_estimation:
        with open(save_path, "w") as json_file:
            json.dump(tale, json_file, indent=2)

    return tale, cost


def fuse_documentation(code, tale, output_path, file_name, file_ext):
    save_path = os.path.join(output_path, file_name)
    logger.info(f"save fused dev tale in: {save_path}")

    if file_ext == ".py":
        aggregator = PythonAggregator()
    elif file_ext == ".php":
        aggregator = PHPAggregator()
    elif file_ext == ".go":
        aggregator = GoAggregator()
    elif file_ext == ".js":
        aggregator = JavascriptAggregator()

    fused_tale = aggregator.document(code=code, documentation=tale)
    with open(save_path, "w") as file:
        file.write(fused_tale)


@click.command()
@click.option(
    "-p",
    "--path",
    "path",
    required=True,
    help="The path to the repository, folder, or file",
)
@click.option(
    "-r",
    "--recursive",
    "recursive",
    is_flag=True,
    default=False,
    help="Allows to explore subfolders.",
)
@click.option(
    "-f",
    "--fuse",
    "fuse",
    is_flag=True,
    default=False,
    help="Adds the docstrings inside the code file.",
)
@click.option(
    "-o",
    "--output-path",
    "output_path",
    required=False,
    default=DEFAULT_OUTPUT_PATH,
    help="The destination folder where you want to save the documentation outputs",
)
@click.option(
    "-n",
    "--model-name",
    "model_name",
    required=False,
    default=DEFAULT_MODEL_NAME,
    help="The OpenAI model name you want to use. \
    https://platform.openai.com/docs/models",
)
@click.option(
    "--debug",
    "debug",
    is_flag=True,
    default=False,
    help="Mock answer and avoid GPT calls",
)
@click.option(
    "--estimation",
    "cost_estimation",
    is_flag=True,
    default=False,
    help="When true, estimate the cost of openAI's API usage, without making any call",
)
def main(
    path: str,
    recursive: bool,
    fuse: bool,
    output_path: str = DEFAULT_OUTPUT_PATH,
    model_name: str = DEFAULT_MODEL_NAME,
    debug: bool = False,
    cost_estimation: bool = False,
):
    load_dotenv()

    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = getpass.getpass(
            prompt="Enter your OpenAI API key: "
        )

    if os.path.isdir(path):
        if recursive:
            logger.info("Processing repository")
            price = process_repository(
                root_path=path,
                output_path=output_path,
                model_name=model_name,
                fuse=fuse,
                debug=debug,
                cost_estimation=cost_estimation,
            )
        else:
            logger.info("Processing folder")
            _, price = process_folder(
                folder_path=path,
                output_path=output_path,
                model_name=model_name,
                fuse=fuse,
                debug=debug,
                cost_estimation=cost_estimation,
            )
    elif os.path.isfile(path):
        logger.info("Processing file")
        _, price = process_file(
            file_path=path,
            output_path=output_path,
            model_name=model_name,
            fuse=fuse,
            debug=debug,
            cost_estimation=cost_estimation,
        )

    else:
        raise f"Invalid input path {path}. Path must be a directory or code file."

    if cost_estimation:
        logger.info(f"Approximate cost: {price}")
    else:
        logger.info(f"Total cost: {price}")


if __name__ == "__main__":
    main()

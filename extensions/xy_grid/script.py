import os
import json
import datetime
import random
import time

import gradio as gr
import modules.shared as shared
import pyparsing as pp

from modules.chat import chatbot_wrapper, load_character
from modules.html_generator import convert_to_markdown
from pathlib import Path

# Global variables
axis_type = {'x': "prompts", 'y': "presets"}
custom_state = {}
gen_output = []
axis_options = ["prompts", "presets", "characters", "seed", "max_new_tokens", "temperature", "top_p", "top_k", "typical_p", "repetition_penalty", "encoder_repetition_penalty", "no_repeat_ngram_size", "min_length"]

# I had to steal this from server.py because the program freaks out if I try to `import server`
def load_preset_values(preset_menu, state):
    generate_params = {
        'do_sample': True,
        'temperature': 1,
        'top_p': 1,
        'typical_p': 1,
        'repetition_penalty': 1,
        'encoder_repetition_penalty': 1,
        'top_k': 50,
        'num_beams': 1,
        'penalty_alpha': 0,
        'min_length': 0,
        'length_penalty': 1,
        'no_repeat_ngram_size': 0,
        'early_stopping': False,
    }
    with open(Path(f'presets/{preset_menu}.txt'), 'r') as infile:
        preset = infile.read()
    for i in preset.splitlines():
        i = i.rstrip(',').strip().split('=')
        if len(i) == 2 and i[0].strip() != 'tokens':
            generate_params[i[0].strip()] = eval(i[1].strip())
    generate_params['temperature'] = min(1.99, generate_params['temperature'])

    state.update(generate_params)
    custom_state['preset_menu'] = preset_menu
    return state, *[generate_params[k] for k in ['do_sample', 'temperature', 'top_p', 'typical_p', 'repetition_penalty', 'encoder_repetition_penalty', 'top_k', 'min_length', 'no_repeat_ngram_size', 'num_beams', 'penalty_alpha', 'length_penalty', 'early_stopping']]


# Get all of the characters from the character folder
def get_characters():
    paths = (x for x in Path('characters').iterdir() if x.suffix in ('.json', '.yaml', '.yml'))
    instructors = []
    filenames = sorted(os.listdir("characters/instruction-following/"))
    for file in filenames:
        instructor = "instruction-following/" + file[:-5]
        instructors.append(instructor)
    return ", ".join(['None'] + sorted(set((k.stem for k in paths if k.stem != "instruction-following")), key=str.lower) + instructors)


# Get all of the instruction following templates from the character folder
def get_instruct():
    paths = (x for x in Path('characters/instruction-following').iterdir() if x.suffix in ('.json', '.yaml', '.yml'))
    return ", ".join(['None'] + sorted(set((k.stem for k in paths)), key=str.lower))


# Get all of the presets from the presets folder
def get_presets():
    presets = []
    filenames = sorted(os.listdir("presets/"))
    for file in filenames:
        preset = file[:-4]
        presets.append(preset)
    presets.remove("Verbose (Beam Search)")
    return ", ".join(presets)


# Returns the correct results for the axis type chosen by the axis dropdown box
def fill_axis(option):
    global custom_state
    if option == "presets":
        return gr.update(label=option, value=get_presets())
    elif option == "characters":
        return gr.update(label=option, value=get_characters())
    elif option == "instruction template":
        return gr.update(label=option, value=get_instruct())
    elif option == "prompts":
        return gr.update(label=option, value=custom_state['textbox'])
    else:
        return gr.update(label=option, value=custom_state[option])


# Sets the type of data each axis will use
def set_axis(x, y):
    global axis_type
    axis_type.update({'x': x})
    axis_type.update({'y': y})


# Parse the type of the X axis and alter custom_state accordingly
# If you want to add more axes, this is where you would do it.
# Add logic here and include it in axis_options
def parse_axis(axis, value):
    global custom_state
    global axis_type

    # PRESETS
    if axis_type[axis] == "presets":
        if value.strip() != "":
            custom_state = load_preset_values(value.strip(), custom_state)[0]
        else:
            custom_state = load_preset_values(shared.gradio['preset_menu'].value, custom_state)[0]
    # CHARACTERS
    elif axis_type[axis] == "characters":
        if value.split("/")[0] == "instruction-following":
            custom_state['mode'] = "instruct"
        else:
            custom_state['mode'] = "cai-chat"
        value = value.split("/")[-1]
        if custom_state['mode'] == "instruct":
            char_type = 'instruction_template'
        else:
            char_type = 'character_menu'
        if value.strip() != "":
            custom_state[char_type] = value.strip()
        else:
            custom_state[char_type] = shared.gradio[char_type].value
        custom_state.update({k: v for k, v in zip(['name1', 'name2', 'character_picture', 'greeting', 'context', 'end_of_turn', 'display'], load_character(custom_state[char_type], custom_state['name1'], custom_state['name2'], custom_state['mode']))})
    # FLOATS
    elif axis_type[axis] in ("seed", "temperature", "top_p", "typical_p", "repetition_penalty", "encoder_repetition_penalty"):
        if value.strip() != "":
            custom_state[axis_type[axis]] = float(value.strip())
        else:
            custom_state[axis_type[axis]] = shared.gradio[axis_type[axis]].value
    # INTS
    elif axis_type[axis] in ("top_k", "max_new_tokens", "no_repeat_ngram_size", "min_length"):
        if value.strip() != "":
            custom_state[axis_type[axis]] = int(value.strip())
        else:
            custom_state[axis_type[axis]] = shared.gradio[axis_type[axis]].value
    # ANY
    else:
        if value.strip() != "":
            custom_state[axis_type[axis]] = value.strip()
        else:
            custom_state[axis_type[axis]] = shared.gradio[axis_type[axis]].value
    return None


# The main function that generates the grid
def run(constant_seed, seed_value, use_history, x="", y=""):
    global custom_state
    global gen_output
    global axis_type

    # Error handling
    if axis_type['x'] == axis_type['y']:
        return "<h1><span style=\"color: red;\">ERROR: both axes cannot be the same setting</span>"
    if x.strip() == '' and y.strip() == '':
        return "<h1><span style=\"color: red;\">ERROR: both fields are empty</span>"

    shared.args.no_stream = True

    # Backup our parameters so we can put everything back how it was before we started
    temp_internal = shared.history['internal'].copy()
    temp_visible = shared.history['visible'].copy()
    temp_custom_state = custom_state.copy()

    # Handle the constant seed value
    if constant_seed:
        if seed_value == "-1":
            custom_state['seed'] = random.randint(1, 2**31)
        else:
            custom_state['seed'] = seed_value


    # Gather output json info, from before the X/Y parameters take effect
    output_json = {k: custom_state[k] for k in shared.input_elements}

    # This was causing problems when the custom stopping strings was set to None
    if custom_state['custom_stopping_strings'] is None:
        custom_state['custom_stopping_strings'] = ""

    # Have to format the strings because gradio makes it difficult to pass lists around
    x_strings = pp.common.comma_separated_list.parseString(x).asList()
    y_strings = pp.common.comma_separated_list.parseString(y).asList()

    # If someone uses "-1" for a seed axis, we don't want it generating a new seed for every cell of the grid
    if axis_type['x'] == "seed":
        x_strings = [str(random.randint(1, 2**31)) if seed in ('-1','-1.0') else seed for seed in x_strings]
    if axis_type['y'] == "seed":
        y_strings = [str(random.randint(1, 2**31)) if seed in ('-1','-1.0') else seed for seed in y_strings]

    cell_count = len(x_strings) + 1
    output =  "<style>table {table-layout: fixed; overflow: scroll; border-collapse: collapse;border: 1px solid black;} th {width: calc(100% / " + str(cell_count * len(x_strings)) + "); min-width: 100px; border: 1px solid black; padding: 5px;} td {width: calc(100% / " + str(cell_count) + "); min-width: 300px; border: 1px solid black; padding: 5px;} em {color: gray} body {font-family: 'Helvetica', Arial, sans-serif; }</style><table><thead>" + f"<tr><th>X={axis_type['x']}<br>Y={axis_type['y']}</th>"

    # Make the grid
    for i in x_strings:
        output = output + f"<th>{i.strip()}</th>"
    output = output + "</thead><tbody>"
    for i in y_strings:
        output = output + f"<tr><th>{i.strip()}</th>"
        for j in x_strings:

            # parse the type of the axes and alter custom_state accordingly
            if axis_type['x'] == "prompts":
                parse_axis("y", i)
            elif axis_type['y'] == "prompts":
                parse_axis("x", j)
            elif y_strings != '' and x_strings != '':
                # in this case, we need to make sure we parse presets first, so it doesn't overwrite lower level settings
                if axis_type['y'] == "presets":
                    parse_axis("y", i)
                    parse_axis("x", j)
                else:
                    parse_axis("x", j)
                    parse_axis("y", i)
            elif x_strings != '':
                parse_axis("x", j)
            elif y_strings != '':
                parse_axis("y", i)
            else:
                return "<h1><span style=\"color: red;\">ERROR: unknown error</span>"

            # Determine whether or not we are including the character's chat history with the user
            if not use_history:
                shared.history['internal'] = shared.history['internal'][:1]
                shared.history['visible'] = shared.history['visible'][:1]

            # Clear all history for instruct mode
            if custom_state['mode'] == "instruct":
                shared.history['internal'].clear()
                shared.history['visible'].clear()

            # This is the part that actually does the generating
            if axis_type['x'] == "prompts":
                for new in chatbot_wrapper(j.strip().strip('"'), custom_state):
                    gen_output = new
            elif axis_type['y'] == "prompts":
                for new in chatbot_wrapper(i.strip().strip('"'), custom_state):
                    gen_output = new
            else:
                for new in chatbot_wrapper(custom_state['textbox'].strip(), custom_state):
                    gen_output = new

            # Sometimes it the generation kicks back nothing and it causes problems
            if len(gen_output) == 0:
                gen_output = [['','']]

            # Turn the output into HTML for our table
            user_output = convert_to_markdown(gen_output[-1][0])
            bot_output = convert_to_markdown(gen_output[-1][1])
            if custom_state['mode'] == 'instruct':
                output = output + f"<td><h3><b>{custom_state['name1']}</b></h3> {user_output}<h3><b>{custom_state['name2']}</b></h3> {bot_output}</td>"
            else:
                output = output + f"<td><h3><b>{custom_state['name1']}:</b></h3> {user_output}<h3><b>{custom_state['name2']}:</b></h3> {bot_output}</td>"

            # Remove the last outputs, so they don't influence future generations
            if custom_state['mode'] == 'instruct':
                shared.history['internal'].clear()
                shared.history['visible'].clear()
            else:
                if len(shared.history['internal']) > 1:
                    shared.history['internal'].pop()
                elif len(shared.history['internal']) == 1:
                    if shared.history['internal'] == gen_output:
                        shared.history['internal'].clear()
                if len(shared.history['visible']) > 1:
                    shared.history['visible'].pop()
                elif len(shared.history['visible']) == 1:
                    if shared.history['visible'] == gen_output:
                        shared.history['visible'].clear()

        output = output + "</tr>"
    output = output + "</tbody></table>"

    # Save the output to a file
    output_folder = Path("extensions/xy_grid/outputs")
    if not Path(output_folder).exists():
        os.mkdir(output_folder)
    output_filename = Path(f"{datetime.datetime.now().strftime('%Y_%m_%d_%H%M%S')}")
    with open(Path(f"{output_folder}/{output_filename}.html"), 'w') as outfile:
        outfile.write(output)
    with open(Path(f"{output_folder}/{output_filename}.json"), 'w') as outparams:
        outparams.write(json.dumps(output_json))

    # Include a link to the generated HTML file
    output = f"<h3><a href=\"file/extensions/xy_grid/outputs/{output_filename}.html\" target=\"_blank\">[ <em>open html file 🔗</em> ]</a></h3><br><br>" + output

    # Clean up the changes that were made during this generation
    shared.history['internal'] = temp_internal.copy()
    shared.history['visible'] = temp_visible.copy()
    custom_state = temp_custom_state.copy()

    return output


# Necessary for some stuff because gradio
def swap_axes(x_menu, x_data, y_menu, y_data):
    return y_menu, y_data, gr.update(label=y_menu), x_menu, x_data, gr.update(label=x_menu)


def toggle_visible(var):
    if not var:
        custom_state['seed'] = -1
    return gr.update(visible=var)


# Create the interface for the extension (this runs first)
def ui():
    global custom_state
    global axis_type

    # Grab all the variable from shared.gradio and put them in the custom_state dictionary
    custom_state.update({k: v for k, v in zip([key for key in shared.gradio if not isinstance(shared.gradio[key], (gr.Blocks, gr.Button, gr.State))], [shared.gradio[k].value for k in [key for key in shared.gradio] if not isinstance(shared.gradio[k], (gr.Blocks, gr.Button, gr.State))])})

    # Track changes to all variables in shared.gradio
    shared.gradio['add_bos_token'].change(lambda x: custom_state.update({'add_bos_token': x}), shared.gradio['add_bos_token'], [])
    shared.gradio['auto_devices'].change(lambda x: custom_state.update({'auto_devices': x}), shared.gradio['auto_devices'], [])
    shared.gradio['ban_eos_token'].change(lambda x: custom_state.update({'ban_eos_token': x}), shared.gradio['ban_eos_token'], [])
    shared.gradio['bf16'].change(lambda x: custom_state.update({'bf16': x}), shared.gradio['bf16'], [])
    shared.gradio['bool_menu'].change(lambda x: custom_state.update({'bool_menu': x}), shared.gradio['bool_menu'], [])
    shared.gradio['character_menu'].change(lambda x: custom_state.update({'character_menu': x}), shared.gradio['character_menu'], [])
    shared.gradio['character_picture'].change(lambda x: custom_state.update({'character_picture': x}), shared.gradio['character_picture'], [])
    shared.gradio['chat_generation_attempts'].change(lambda x: custom_state.update({'chat_generation_attempts': x}), shared.gradio['chat_generation_attempts'], [])
    shared.gradio['chat_prompt_size'].change(lambda x: custom_state.update({'chat_prompt_size': x}), shared.gradio['chat_prompt_size'], [])
    shared.gradio['context'].change(lambda x: custom_state.update({'context': x}), shared.gradio['context'], [])
    shared.gradio['cpu'].change(lambda x: custom_state.update({'cpu': x}), shared.gradio['cpu'], [])
    shared.gradio['cpu_memory'].change(lambda x: custom_state.update({'cpu_memory': x}), shared.gradio['cpu_memory'], [])
    shared.gradio['custom_model_menu'].change(lambda x: custom_state.update({'custom_model_menu': x}), shared.gradio['custom_model_menu'], [])
    shared.gradio['custom_stopping_strings'].change(lambda x: custom_state.update({'custom_stopping_strings': x}), shared.gradio['custom_stopping_strings'], [])
    shared.gradio['disk'].change(lambda x: custom_state.update({'disk': x}), shared.gradio['disk'], [])
    shared.gradio['display'].change(lambda x: custom_state.update({'display': x}), shared.gradio['display'], [])
    shared.gradio['do_sample'].change(lambda x: custom_state.update({'do_sample': x}), shared.gradio['do_sample'], [])
    shared.gradio['download'].change(lambda x: custom_state.update({'download': x}), shared.gradio['download'], [])
    shared.gradio['early_stopping'].change(lambda x: custom_state.update({'early_stopping': x}), shared.gradio['early_stopping'], [])
    shared.gradio['encoder_repetition_penalty'].change(lambda x: custom_state.update({'encoder_repetition_penalty': x}), shared.gradio['encoder_repetition_penalty'], [])
    shared.gradio['end_of_turn'].change(lambda x: custom_state.update({'end_of_turn': x}), shared.gradio['end_of_turn'], [])
    shared.gradio['extensions_menu'].change(lambda x: custom_state.update({'extensions_menu': x}), shared.gradio['extensions_menu'], [])
    shared.gradio['gpu_memory_0'].change(lambda x: custom_state.update({'gpu_memory_0': x}), shared.gradio['gpu_memory_0'], [])
    shared.gradio['greeting'].change(lambda x: custom_state.update({'greeting': x}), shared.gradio['greeting'], [])
    shared.gradio['groupsize'].change(lambda x: custom_state.update({'groupsize': x}), shared.gradio['groupsize'], [])
    shared.gradio['instruction_template'].change(lambda x: custom_state.update({'instruction_template': x}), shared.gradio['instruction_template'], [])
    shared.gradio['interface_modes_menu'].change(lambda x: custom_state.update({'interface_modes_menu': x}), shared.gradio['interface_modes_menu'], [])
    shared.gradio['length_penalty'].change(lambda x: custom_state.update({'length_penalty': x}), shared.gradio['length_penalty'], [])
    shared.gradio['load_in_8bit'].change(lambda x: custom_state.update({'load_in_8bit': x}), shared.gradio['load_in_8bit'], [])
    shared.gradio['lora_menu'].change(lambda x: custom_state.update({'lora_menu': x}), shared.gradio['lora_menu'], [])
    shared.gradio['max_new_tokens'].change(lambda x: custom_state.update({'max_new_tokens': x}), shared.gradio['max_new_tokens'], [])
    shared.gradio['min_length'].change(lambda x: custom_state.update({'min_length': x}), shared.gradio['min_length'], [])
    shared.gradio['mode'].change(lambda x: custom_state.update({'mode': x}), shared.gradio['mode'], [])
    shared.gradio['model_menu'].change(lambda x: custom_state.update({'model_menu': x}), shared.gradio['model_menu'], [])
    shared.gradio['model_status'].change(lambda x: custom_state.update({'model_status': x}), shared.gradio['model_status'], [])
    shared.gradio['model_type'].change(lambda x: custom_state.update({'model_type': x}), shared.gradio['model_type'], [])
    shared.gradio['name1'].change(lambda x: custom_state.update({'name1': x}), shared.gradio['name1'], [])
    shared.gradio['name2'].change(lambda x: custom_state.update({'name2': x}), shared.gradio['name2'], [])
    shared.gradio['no_repeat_ngram_size'].change(lambda x: custom_state.update({'no_repeat_ngram_size': x}), shared.gradio['no_repeat_ngram_size'], [])
    shared.gradio['num_beams'].change(lambda x: custom_state.update({'num_beams': x}), shared.gradio['num_beams'], [])
    shared.gradio['penalty_alpha'].change(lambda x: custom_state.update({'penalty_alpha': x}), shared.gradio['penalty_alpha'], [])
    shared.gradio['pre_layer'].change(lambda x: custom_state.update({'pre_layer': x}), shared.gradio['pre_layer'], [])
    shared.gradio['preset_menu'].change(lambda x: custom_state.update({'preset_menu': x}), shared.gradio['preset_menu'], [])
    shared.gradio['repetition_penalty'].change(lambda x: custom_state.update({'repetition_penalty': x}), shared.gradio['repetition_penalty'], [])
    shared.gradio['seed'].change(lambda x: custom_state.update({'seed': x}), shared.gradio['seed'], [])
    shared.gradio['skip_special_tokens'].change(lambda x: custom_state.update({'skip_special_tokens': x}), shared.gradio['skip_special_tokens'], [])
    shared.gradio['softprompts_menu'].change(lambda x: custom_state.update({'softprompts_menu': x}), shared.gradio['softprompts_menu'], [])
    shared.gradio['stop_at_newline'].change(lambda x: custom_state.update({'stop_at_newline': x}), shared.gradio['stop_at_newline'], [])
    shared.gradio['temperature'].change(lambda x: custom_state.update({'temperature': x}), shared.gradio['temperature'], [])
    shared.gradio['textbox'].change(lambda x: custom_state.update({'textbox': x}), shared.gradio['textbox'], [])
    shared.gradio['top_k'].change(lambda x: custom_state.update({'top_k': x}), shared.gradio['top_k'], [])
    shared.gradio['top_p'].change(lambda x: custom_state.update({'top_p': x}), shared.gradio['top_p'], [])
    shared.gradio['truncation_length'].change(lambda x: custom_state.update({'truncation_length': x}), shared.gradio['truncation_length'], [])
    shared.gradio['typical_p'].change(lambda x: custom_state.update({'typical_p': x}), shared.gradio['typical_p'], [])
    shared.gradio['upload_chat_history'].change(lambda x: custom_state.update({'upload_chat_history': x}), shared.gradio['upload_chat_history'], [])
    shared.gradio['upload_img_bot'].change(lambda x: custom_state.update({'upload_img_bot': x}), shared.gradio['upload_img_bot'], [])
    shared.gradio['upload_img_tavern'].change(lambda x: custom_state.update({'upload_img_tavern': x}), shared.gradio['upload_img_tavern'], [])
    shared.gradio['upload_json'].change(lambda x: custom_state.update({'upload_json': x}), shared.gradio['upload_json'], [])
    shared.gradio['upload_softprompt'].change(lambda x: custom_state.update({'upload_softprompt': x}), shared.gradio['upload_softprompt'], [])
    shared.gradio['wbits'].change(lambda x: custom_state.update({'wbits': x}), shared.gradio['wbits'], [])
    shared.gradio['your_picture'].change(lambda x: custom_state.update({'your_picture': x}), shared.gradio['your_picture'], [])
    shared.gradio['mode'].change(lambda x: custom_state.update({'mode': x}), shared.gradio['mode'], [])

    # UI for the extension
    with gr.Accordion("XY Grid", open=True):

        # Axis selections and inputs
        with gr.Row():
            x_type = gr.Dropdown(label='X Axis', choices=axis_options, value="prompts", interactive=True)
            x_input = gr.Textbox(label=x_type.value, interactive=True)
        with gr.Row():
            y_type = gr.Dropdown(label='Y Axis', choices=axis_options, value="presets", interactive=True)
            y_input = gr.Textbox(label=y_type.value, value=get_presets, interactive=True)
        x_type.select(set_axis, [x_type, y_type], []).then(fill_axis, x_type, x_input)
        y_type.select(set_axis, [x_type, y_type], []).then(fill_axis, y_type, y_input)
        x_type.change(set_axis, [x_type, y_type], [])
        y_type.change(set_axis, [x_type, y_type], [])

        with gr.Row():
            swap_xy = gr.Button(value='Swap X/Y Axes')
        with gr.Row():
            seed_input = gr.Checkbox(label='Use a constant seed', value=False)
            use_history = gr.Checkbox(label='Use character\'s chat history', value=False)
        with gr.Row():
            seed_value = gr.Textbox(label='Seed', value="-1", visible=False, interactive=True)
        seed_input.change(toggle_visible, seed_input, seed_value)
        swap_xy.click(swap_axes, [x_type, x_input, y_type, y_input], [x_type, x_input, x_input, y_type, y_input, y_input])

        generate_grid = gr.Button("generate_grid")
        custom_chat = gr.HTML(value="")

        generate_grid.click(run, [seed_input, seed_value, use_history, x_input, y_input], custom_chat)
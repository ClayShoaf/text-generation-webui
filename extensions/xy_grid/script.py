import os
import json
import datetime

import gradio as gr
import modules.shared as shared
import modules.ui
import pyparsing as pp

from modules.chat import chatbot_wrapper
from pathlib import Path

testd = {}
custom_state = {}
custom_output = []

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
    return state, *[generate_params[k] for k in ['do_sample', 'temperature', 'top_p', 'typical_p', 'repetition_penalty', 'encoder_repetition_penalty', 'top_k', 'min_length', 'no_repeat_ngram_size', 'num_beams', 'penalty_alpha', 'length_penalty', 'early_stopping']]


# Get all of the presets from the presets folder
def get_presets():
    global custom_state
    presets = []
    filenames = os.listdir("presets/")
    for file in filenames:
        preset = file[:-4]
        presets.append(preset)
        custom_state = load_preset_values(preset, custom_state)[0]
    return ", ".join(presets)

# This is a workaround function because gradio has to access parameters if you want them to be current
def get_params(*args):
    global custom_state
    custom_state = modules.ui.gather_interface_values(*args)
    return json.dumps(custom_state)

# The main function that generates the output, formats the html table, and returns it to the interface
def run(x="", y=""):
    global custom_state
    global custom_output
    custom_state['seed'] = "420691337"
    

    output = "<style>table {border-collapse: collapse;border: 1px solid black;}th, td {border: 1px solid black;padding: 5px;}</style><table><thead><tr><th></th>"

    # Have to format the strings because gradio makes it difficult to pass lists around
    x_strings = pp.common.comma_separated_list.parseString(x).asList()
    y_strings = pp.common.comma_separated_list.parseString(y).asList()

    for i in y_strings:
        output = output + f"<th>{i.strip()}</th>"
    output = output + "</thead><tbody>"
    for i in x_strings:
        output = output + f"<tr><th>{i}</th>"
        if y_strings[0] != '':
            for j in y_strings:
                custom_state = load_preset_values(j.strip(), custom_state)[0]

                # This is the part that actually does the generating
                for new in chatbot_wrapper(i.strip(), custom_state):
                    custom_output = new

                output = output + f"<td><b>{custom_state['name1']}:</b> {custom_output[-1][0]}<br><b>{custom_state['name2']}:</b> {custom_output[-1][1]}</td>"
                custom_output.pop()
                shared.history['internal'].pop()

            output = output + "</tr>"
        else:
                for new in chatbot_wrapper(i.strip(), custom_state):
                    custom_output = new
                output = output + f"<td><b>{custom_state['name1']}:</b> {custom_output[-1][0]}<br><b>{custom_state['name2']}:</b> {custom_output[-1][1]}</td>"

                # Remove the last outputs so they don't influence future generations
                custom_output.pop()
                shared.history['internal'].pop()

        output = output + "</tr>"
    output = output + "</tbody></table>"

    # Save the output to a file
    # Useful for large grids that don't display well in gradio
    save_filename = f"{datetime.datetime.now().strftime('%Y_%m_%d_%f')}.html"
    with open(Path(f"extensions/xy_grid/outputs/{save_filename}"), 'w') as outfile:
        outfile.write(output)

    # Trying to include a link to easily open the html file in a new tab, but I think this is gonna be more confusing than I expected
    output = output + f"<br><br><a href=\"file/extensions/xy_grid/outputs/{save_filename}\" target=\"_blank\">open html file</a>"
    return output

def testf():
    global testd
    print("testing function activated")

# Create the interface for the extension (this runs first)
def ui():
    # Track changes
    shared.gradio['max_new_tokens'].change(lambda x: testd.update({'max_new_tokens': x}), shared.gradio['max_new_tokens'], [])
    shared.gradio['seed'].change(lambda x: testd.update({'seed': x}), shared.gradio['seed'], [])
    shared.gradio['temperature'].change(lambda x: testd.update({'temperature': x}), shared.gradio['temperature'], [])
    shared.gradio['top_p'].change(lambda x: testd.update({'top_p': x}), shared.gradio['top_p'], [])
    shared.gradio['top_k'].change(lambda x: testd.update({'top_k': x}), shared.gradio['top_k'], [])
    shared.gradio['typical_p'].change(lambda x: testd.update({'typical_p': x}), shared.gradio['typical_p'], [])
    shared.gradio['repetition_penalty'].change(lambda x: testd.update({'repetition_penalty': x}), shared.gradio['repetition_penalty'], [])
    shared.gradio['encoder_repetition_penalty'].change(lambda x: testd.update({'encoder_repetition_penalty': x}), shared.gradio['encoder_repetition_penalty'], [])
    shared.gradio['no_repeat_ngram_size'].change(lambda x: testd.update({'no_repeat_ngram_size': x}), shared.gradio['no_repeat_ngram_size'], [])
    shared.gradio['min_length'].change(lambda x: testd.update({'min_length': x}), shared.gradio['min_length'], [])
    shared.gradio['do_sample'].change(lambda x: testd.update({'do_sample': x}), shared.gradio['do_sample'], [])
    shared.gradio['penalty_alpha'].change(lambda x: testd.update({'penalty_alpha': x}), shared.gradio['penalty_alpha'], [])
    shared.gradio['num_beams'].change(lambda x: testd.update({'num_beams': x}), shared.gradio['num_beams'], [])
    shared.gradio['length_penalty'].change(lambda x: testd.update({'length_penalty': x}), shared.gradio['length_penalty'], [])
    shared.gradio['early_stopping'].change(lambda x: testd.update({'early_stopping': x}), shared.gradio['early_stopping'], [])
    shared.gradio['add_bos_token'].change(lambda x: testd.update({'add_bos_token': x}), shared.gradio['add_bos_token'], [])
    shared.gradio['ban_eos_token'].change(lambda x: testd.update({'ban_eos_token': x}), shared.gradio['ban_eos_token'], [])
    shared.gradio['truncation_length'].change(lambda x: testd.update({'truncation_length': x}), shared.gradio['truncation_length'], [])
    shared.gradio['custom_stopping_strings'].change(lambda x: testd.update({'custom_stopping_strings': x}), shared.gradio['custom_stopping_strings'], [])
    shared.gradio['name1'].change(lambda x: testd.update({'name1': x}), shared.gradio['name1'], [])
    shared.gradio['name2'].change(lambda x: testd.update({'name2': x}), shared.gradio['name2'], [])
    shared.gradio['greeting'].change(lambda x: testd.update({'greeting': x}), shared.gradio['greeting'], [])
    shared.gradio['context'].change(lambda x: testd.update({'context': x}), shared.gradio['context'], [])
    shared.gradio['end_of_turn'].change(lambda x: testd.update({'end_of_turn': x}), shared.gradio['end_of_turn'], [])
    shared.gradio['chat_prompt_size'].change(lambda x: testd.update({'chat_prompt_size': x}), shared.gradio['chat_prompt_size'], [])
    shared.gradio['chat_generation_attempts'].change(lambda x: testd.update({'chat_generation_attempts': x}), shared.gradio['chat_generation_attempts'], [])
    shared.gradio['stop_at_newline'].change(lambda x: testd.update({'stop_at_newline': x}), shared.gradio['stop_at_newline'], [])
    shared.gradio['mode'].change(lambda x: testd.update({'mode': x}), shared.gradio['mode'], [])
    shared.gradio['instruction_template'].change(lambda x: testd.update({'instruction_template': x}), shared.gradio['instruction_template'], [])
    shared.gradio['cpu_memory'].change(lambda x: testd.update({'cpu_memory': x}), shared.gradio['cpu_memory'], [])
    shared.gradio['auto_devices'].change(lambda x: testd.update({'auto_devices': x}), shared.gradio['auto_devices'], [])
    shared.gradio['disk'].change(lambda x: testd.update({'disk': x}), shared.gradio['disk'], [])
    shared.gradio['cpu'].change(lambda x: testd.update({'cpu': x}), shared.gradio['cpu'], [])
    shared.gradio['bf16'].change(lambda x: testd.update({'bf16': x}), shared.gradio['bf16'], [])
    shared.gradio['load_in_8bit'].change(lambda x: testd.update({'load_in_8bit': x}), shared.gradio['load_in_8bit'], [])
    shared.gradio['wbits'].change(lambda x: testd.update({'wbits': x}), shared.gradio['wbits'], [])
    shared.gradio['groupsize'].change(lambda x: testd.update({'groupsize': x}), shared.gradio['groupsize'], [])
    shared.gradio['model_type'].change(lambda x: testd.update({'model_type': x}), shared.gradio['model_type'], [])
    shared.gradio['pre_layer'].change(lambda x: testd.update({'pre_layer': x}), shared.gradio['pre_layer'], [])
    shared.gradio['gpu_memory_0'].change(lambda x: testd.update({'gpu_memory_0': x}), shared.gradio['gpu_memory_0'], [])

    with gr.Accordion("XY Grid", open=True):

        global testd
        global testa
        testh = gr.HTML(value="TEST RESULTS")
        testb = gr.Button(value="TEST")
        testb.click(fn=testf, outputs=testh)

        for k in shared.input_elements:
            testd[k] = shared.gradio[k].value
            shared.gradio[k].change(lambda x: testd.update({k: x}), shared.gradio[k], [])
            print(k)

        prompt = gr.Textbox(placeholder="Comma separated prompts go here...", label='Input Prompts', interactive=True)
        with gr.Row():
            presets_box = gr.Textbox(placeholder="Presets go here. Click the buttton to the right...", label='Presets', interactive=True)
            refresh_presets = modules.ui.ToolButton(value='\U0001f504', elem_id='refresh-button')
            refresh_presets.click(fn=get_presets, outputs=presets_box)
        generate_grid = gr.Button("generate_grid")
        with gr.Accordion("Generation Parameters for testing", open=False):
            state = gr.HTML(value="the state will go here")
        custom_chat = gr.HTML(value="")

    generate_grid.click(get_params, [shared.gradio[k] for k in shared.input_elements], state).then(run, [prompt, presets_box], custom_chat)

#  --model oasst-llama13b-4bit-128g

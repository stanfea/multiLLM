# ==============================================================================
# Copyright 2023 VerifAI All Rights Reserved.
# https://www.verifai.ai
# License: 
#
# ==============================================================================


"""Generated by VerifAI
This Python code defines a class called MultiLLM and a main function.

The MultiLLM class is responsible for managing and running multiple language models. It has the following methods:

__init__(self, config, models=None): Initializes the class, taking a config argument and an optional models argument. The config parameter is used to load models from a configuration file, while the models parameter is used to directly pass a list of models to the class.
load_models(self, config): Loads models from a configuration file. This method is not implemented in the code snippet.
__str__(self): Returns a string representation of the MultiLLM object, including the names of the models.
__repr__(self): Returns a string representation of the MultiLLM object, including the features of each model.
run(self, prompt : Prompt): Runs a given prompt through each model concurrently and processes the responses using the Action class. It takes a prompt argument, which is an object of the Prompt class. This method uses multiple threads to run each model and process the responses.
The main function is currently empty and expects command-line arguments.

The remaining code at the bottom is used to parse command-line arguments when the script is executed as the main program. However, the argument parsing functionality is not implemented in the code snippet.
"""

import os
import sys
import types
import json
import argparse
import importlib

import concurrent.futures
import multiprocessing

sys.path.append(os.path.join(os.path.dirname(__file__), "."))

from Prompt import *
from BaseLLM import *
from Action import *

from Redis import *

redisConnected = True
try:
    redis_conn = Redis.connection
except Exception as e:
    log.warn('redis disabled: {0}' .format(str(e)))
    redisConnected = False


# MultiLLM class
class MultiLLM(object):

    model_registry = {}

    def __init__(self, config=None, models=[], model_names=[]):

        self.models = models
        self.model_names = model_names
        
        #registry = Models.model_registry
        if config:
            self.models = self.load_models( config) #reads data
        
    

    def run(self, prompt, action_chain, rank_chain):
        """
        """
        responses = {}

        with multiprocessing.Pool() as pool:
            # Create a list of (model_name, Future) tuples for each model response
            model_and_future = []
            for model_name in self.model_names:
                print('calling model: {0}' .format(model_name))
                model = MultiLLM.model_registry[model_name]
                if not model:
                    continue
                #print("model {0} : {1}" .format(model_name, dir(model)))
                model_and_future.append((model_name, pool.apply_async(model.get_response, (prompt,))))

            # Process the results of each model using the Action class
            for model_name, future in model_and_future:
                try:
                    response = future.get()
                    responses[model_name] = response
                except Exception as exc:
                    print(f"(MultiLLM) Error: occurred: {exc}")
                    responses[model_name] = f"(MultiLLM) Error: occurred: {exc}"


                try:
                    # Process the response using the Action class concurrently for each action_callback
                    if action_chain:
                        try:
                            result = action_chain.apply(response)
                            responses[model_name] = result
                        except Exception as e:
                            print('(MultiLLM) : Error from action_chain.apply() {0}' .format(str(e)))
                        
                    else:
                        result = response
                        
                        #print("Result:", result)
                        """
                            with multiprocessing.Pool() as action_pool:
                            action_results = action_pool.apply_async(action_chain.apply, (response,))
                            print("Action result:", action_results.get())
                            # You can choose to do something with 'action_results' if needed.
                            """
                        
                except Exception as exc:
                    print(f"(MultiLLM) Error1: occurred: {exc}")
                    responses[model_name] = f"Error occurred: {exc}"

        if not rank_chain:
            return responses
        else:
            return rank_chain.apply(responses)


    
    def load_models(self, config):
        """ Load Models from a config file """
        
        if config:
            try:
                with open(config) as f:
                    conf_data = json.load(f)
                
            except Exception as e:
                print("could not read config file {0} : {1}" .format(config, str(e)))
                return

        loaded_llms = {}
        if conf_data is not None:

            try:
                llms = conf_data["Config"]["MultiLLM"]["llms"]
                for llm in llms:
                    model_file = None
                    model = None
                    credentials = None
                    class_name = None
                    try:
                        model_file = llm['file']
                        model =  llm['model']
                        credentials = llm['credentials']
                        class_name = llm['class_name']
                    except:
                        print('ERROR (MultiLLM): could not parse llm {0} from config, skipping' .format(llm))
                        pass
                    
                    # load model file..
                    # Check if full path of file exists, else see if path relative to package-source exists
                    if not os.path.exists(os.path.abspath(model_file)):
                        rel_path, cfile = script_path = os.path.split(os.path.abspath(__file__))
                        mfile = os.path.join(rel_path, model_file)
                    else:
                        mfile = model_file
                    #print('mfile {0}' .format(mfile))
                    head , tail = os.path.split(os.path.abspath(mfile))
                    sys.path.append(head)
                    model_file_name = os.path.splitext(tail)[0]
                    #print("loading llm  head: {0} model_file_name {1}" .format(head, model_file_name))
                    print('loading module {0}...' .format(os.path.abspath(mfile)))
                    try:
                        llm_model = importlib.import_module(model_file_name)
                        loaded_llms[model_file_name] = llm_model
                        print('finished loading module {0}' .format(model_file_name))
                        # Add model name to class var
                        self.model_names.append(class_name)
                        self.register_model(llm_model, llm)
                    except Exception as e:
                        print("ERROR (MultiLLM): could not load model from config file '{0}' : {1}, skipping"
                              .format(model_file_name, str(e)))
                    
            except Exception as e:
                print("could not read llms from config file {0} : {1}" .format(config, str(e)))
                return

        if len(loaded_llms):
            print('loaded llms: {0}' .format(loaded_llms))
            
        return

    def __str__(self):
        return f"MultiLLM with {self.models}"

    def __repr__(self):
        return f"MultiLLM with {[m.features for m in self.models]}"
        


    # questions
    # we want interfaces being defined, and the class itself (not object) to be passed into the register_model() method
    # actual calling and setting of these models can be done by the user
    # LLM_Model.add_model(model_name(params))
    @staticmethod
    def register_model(  model: BaseLLM , class_config = None):
        if not class_config:
            class_name = model.__name__
        else:
            class_name = class_config['class_name']
        try: 
            class_ = getattr(model, class_name)   
            instance = class_() 
            """ Figure out why we can't pass this into init() """
            instance.class_name = class_name
            instance.credentials = class_config['credentials']
            instance.model = class_config['model']

            MultiLLM.model_registry[class_name] = instance
            print('registered model {0} {1}' .format(class_name, instance))
        except Exception as e:
            print("ERROR: (MultiLLM): could not register model {0} : {1}" .format(class_name, str(e)))
        



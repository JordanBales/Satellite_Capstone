#####################################################################################################################################################################
# xView2                                                                                                                                                            #
# Copyright 2019 Carnegie Mellon University.                                                                                                                        #
# NO WARRANTY. THIS CARNEGIE MELLON UNIVERSITY AND SOFTWARE ENGINEERING INSTITUTE MATERIAL IS FURNISHED ON AN "AS-IS" BASIS. CARNEGIE MELLON UNIVERSITY MAKES NO    #
# WARRANTIES OF ANY KIND, EITHER EXPRESSED OR IMPLIED, AS TO ANY MATTER INCLUDING, BUT NOT LIMITED TO, WARRANTY OF FITNESS FOR PURPOSE OR MERCHANTABILITY,          # 
# EXCLUSIVITY, OR RESULTS OBTAINED FROM USE OF THE MATERIAL. CARNEGIE MELLON UNIVERSITY DOES NOT MAKE ANY WARRANTY OF ANY KIND WITH RESPECT TO FREEDOM FROM PATENT, # 
# TRADEMARK, OR COPYRIGHT INFRINGEMENT.                                                                                                                             #
# Released under a MIT (SEI)-style license, please see LICENSE.md or contact permission@sei.cmu.edu for full terms.                                                 #
# [DISTRIBUTION STATEMENT A] This material has been approved for public release and unlimited distribution.  Please see Copyright notice for non-US Government use  #
# and distribution.                                                                                                                                                 #
# This Software includes and/or makes use of the following Third-Party Software subject to its own license:                                                         #
# 1. SpaceNet (https://github.com/motokimura/spacenet_building_detection/blob/master/LICENSE) Copyright 2017 Motoki Kimura.                                         #
# DM19-0988                                                                                                                                                         #
#####################################################################################################################################################################


from PIL import Image
import time
import numpy as np
import pandas as pd
from tqdm import tqdm
import os
import math
import random
import argparse
import logging
import json
from sys import exit
import cv2
import datetime

import shapely.wkt
import shapely
from shapely.geometry import Polygon
from collections import defaultdict

import tensorflow as tf
import keras
#from model import * 

from keras import Sequential
from keras.layers import Conv2D, MaxPooling2D, Dense
from keras.preprocessing.image import load_img, img_to_array, ImageDataGenerator
#from model import *

# Configurations
NUM_WORKERS = 4
NUM_CLASSES = 4
BATCH_SIZE = 64
NUM_EPOCHS = 120
LEARNING_RATE = 0.0001
RANDOM_SEED = 123
LOG_DIR = '/tmp/inference/classification_log_' + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


damage_intensity_encoding = dict() 
damage_intensity_encoding[3] = 'destroyed' 
damage_intensity_encoding[2] = 'major-damage'
damage_intensity_encoding[1] = 'minor-damage'
damage_intensity_encoding[0] = 'no-damage'


###
# Creates data generator for validation set
###
def create_generator(test_df, test_dir, output_json_path):

    gen = keras.preprocessing.image.ImageDataGenerator(
                             rescale=1.4)

    try:
        gen_flow = gen.flow_from_dataframe(dataframe=test_df,
                                   directory=test_dir,
                                   x_col='uuid',
                                   batch_size=BATCH_SIZE,
                                   shuffle=False,
                                   seed=RANDOM_SEED,
                                   class_mode=None,
                                   target_size=(128, 128),
                                   validate_filenames=False)
        print("completed flow from dataframe")
        print(test_dir)
    except:
        # No polys detected so write out a blank json
        blank = {}
        with open(output_json_path , 'w') as outfile:
            json.dump(blank, outfile)
        exit(0)


    return gen_flow

# Runs inference on given test data and pretrained model
def run_inference(test_data, test_csv, model_weights, output_json_path):

    model = generate_xBD_baseline_model()
    model.load_weights(model_weights)

    adam = keras.optimizers.Adam(lr=LEARNING_RATE,
                                    beta_1=0.9,
                                    beta_2=0.999,
                                    epsilon=None,
                                    decay=0.0,
                                    amsgrad=False)


    model.compile(loss=ordinal_loss, optimizer=adam, metrics=['accuracy'])

    df = pd.read_csv(test_csv)
    print(df.head())
    print("DF OF TEST_CSV")
    print(test_csv)
    print(output_json_path)

    test_gen = create_generator(df, test_data, output_json_path)
    test_gen.reset()
   
    samples = df["uuid"].count()
    print("samples", samples)
    print(test_gen)
    print(type(test_gen))

    steps = np.ceil(samples/BATCH_SIZE)

    tensorboard_callbacks = keras.callbacks.TensorBoard(log_dir=LOG_DIR, histogram_freq=1)

    predictions = model.predict_generator(generator=test_gen,
                    #callbacks=[tensorboard_callbacks],
                    verbose=1)

    predicted_indices = np.argmax(predictions, axis=1)
    predictions_json = dict()
    for i in range(samples):
        filename_raw = test_gen.filenames[i]
        filename = filename_raw.split(".")[0]
        predictions_json[filename] = damage_intensity_encoding[predicted_indices[i]]

    with open(output_json_path , 'w+') as outfile:
        json.dump(predictions_json, outfile)

# Runs inference on given test data and pretrained model
def run_inference2(test_data, model_weights):
    #run_inference2(test_data=poly_dict, model_weights=WEIGHT_DAM_PTH)

    model = generate_xBD_baseline_model()
    model.load_weights(model_weights)

    adam = keras.optimizers.Adam(lr=LEARNING_RATE,
                                    beta_1=0.9,
                                    beta_2=0.999,
                                    epsilon=None,
                                    decay=0.0,
                                    amsgrad=False)


    model.compile(loss=ordinal_loss, optimizer=adam, metrics=['accuracy'])
    test_img_ids = []
    test_img_list = []
    for k, v in test_data.items():
        test_img_ids.append(k)
        #print("v.shape", v.shape)
        img = Image.fromarray(v)
        img = img.resize(size=(128, 128))
        arr = np.array(img)
        arr = 1.4 * arr # because of rescale paramater
        #print ("arr.shape", arr.shape)
        test_img_list.append(arr)

    #np.vstack(test_img_list)
    #test_img_arr = np.stack( test_img_list)
    
    predictions = model.predict(np.array(test_img_list))

    predicted_indices = np.argmax(predictions, axis=1)
    predictions_json = dict()
    for i in range(len(test_img_ids)):
        filename = test_img_ids[i]
        predictions_json[filename] = damage_intensity_encoding[predicted_indices[i]]
    return predictions_json
       
def main():

    parser = argparse.ArgumentParser(description='Run Building Damage Classification Training & Evaluation')
    parser.add_argument('--test_data',
                        required=True,
                        metavar="/path/to/xBD_test_dir",
                        help="Full path to the parent dataset directory")
    parser.add_argument('--test_csv',
                        required=True,
                        metavar="/path/to/xBD_test_csv",
                        help="Full path to the parent dataset directory")
    parser.add_argument('--model_weights',
                        default=None,
                        metavar='/path/to/input_model_weights',
                        help="Path to input weights")
    parser.add_argument('--output_json',
                        required=True,
                        metavar="/path/to/output_json")

    args = parser.parse_args()

    run_inference(args.test_data, args.test_csv, args.model_weights, args.output_json)


if __name__ == '__main__':
    main()

#####################################################################################################################################################################
# xView2                                                                                                                                                            #
# Copyright 2019 Carnegie Mellon University.                                                                                                                        #
# NO WARRANTY. THIS CARNEGIE MELLON UNIVERSITY AND SOFTWARE ENGINEERING INSTITUTE MATERIAL IS FURNISHED ON AN "AS-IS" BASIS. CARNEGIE MELLON UNIVERSITY MAKES NO    #
# WARRANTIES OF ANY KIND, EITHER EXPRESSED OR IMPLIED, AS TO ANY MATTER INCLUDING, BUT NOT LIMITED TO, WARRANTY OF FITNESS FOR PURPOSE OR MERCHANTABILITY,          # 
# EXCLUSIVITY, OR RESULTS OBTAINED FROM USE OF THE MATERIAL. CARNEGIE MELLON UNIVERSITY DOES NOT MAKE ANY WARRANTY OF ANY KIND WITH RESPECT TO FREEDOM FROM PATENT, # 
# TRADEMARK, OR COPYRIGHT INFRINGEMENT.                                                                                                                             #
# Released under a MIT (SEI)-style license, please see LICENSE.md or contact permission@sei.cmu.edu for full terms.                                                 #
# [DISTRIBUTION STATEMENT A] This material has been approved for public release and unlimited distribution.  Please see Copyright notice for non-US Government use  #
# and distribution.                                                                                                                                                 #
# This Software includes and/or makes use of the following Third-Party Software subject to its own license:                                                         #
# 1. SpaceNet (https://github.com/motokimura/spacenet_building_detection/blob/master/LICENSE) Copyright 2017 Motoki Kimura.                                         #
# DM19-0988                                                                                                                                                         #
#####################################################################################################################################################################

from PIL import Image
import time
import numpy as np
import pandas as pd
from tqdm import tqdm
import os
import math
import random
import argparse
import logging
import json
import cv2
import datetime

from sklearn.metrics import f1_score
from sklearn.utils.class_weight import compute_class_weight
import shapely.wkt
import shapely
from shapely.geometry import Polygon
from collections import defaultdict

import tensorflow as tf
import keras
import ast
from keras import Sequential
from keras.layers import Conv2D, MaxPooling2D, Dense, Flatten, Add, Input, Concatenate
from keras.models import Model
from keras.applications.resnet50 import ResNet50
from keras import backend as K


###
# Loss function for ordinal loss from https://github.com/JHart96/keras_ordinal_categorical_crossentropy
###
def ordinal_loss(y_true, y_pred):
    weights = K.cast(K.abs(K.argmax(y_true, axis=1) - K.argmax(y_pred, axis=1))/(K.int_shape(y_pred)[1] - 1), dtype='float32')
    return (1.0 + weights) * keras.losses.categorical_crossentropy(y_true, y_pred )


###
# Generate a simple CNN
###
def generate_xBD_baseline_model():
  weights = 'imagenet'
  inputs = Input(shape=(128, 128, 3))

  base_model = ResNet50(include_top=False, weights=weights, input_shape=(128, 128, 3))

  for layer in base_model.layers:
    layer.trainable = False

  x = Conv2D(32, (5, 5), strides=(1, 1), padding='same', activation='relu', input_shape=(128, 128, 3))(inputs)
  x = MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format=None)(x)

  x = Conv2D(64, (3, 3), strides=(1, 1), padding='same', activation='relu')(x)
  x = MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format=None)(x)

  x = Conv2D(64, (3, 3), strides=(1, 1), padding='same', activation='relu')(x)
  x = MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format=None)(x)

  x = Flatten()(x)

  base_resnet = base_model(inputs)
  base_resnet = Flatten()(base_resnet)

  concated_layers = Concatenate()([x, base_resnet])

  concated_layers = Dense(2024, activation='relu')(concated_layers)
  concated_layers = Dense(524, activation='relu')(concated_layers)
  concated_layers = Dense(124, activation='relu')(concated_layers)
  output = Dense(4, activation='relu')(concated_layers)

  model = Model(inputs=inputs, outputs=output)
  return model
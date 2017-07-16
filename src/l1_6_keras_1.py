#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from keras import layers
from keras import models
from keras import optimizers

import model_base_keras

import data_clean_3_nans as data
#import features_text_2 as fea_1
import features_wa_1 as fea_2
#import features_misc_2 as fea_3

class model(model_base_keras.KerasModelBase):
    def __init__(self):
        name = 'l1_6_keras_1'
        debug = False
        public_score = None
        super().__init__(name, data, [fea_2], debug, public_score)

    def build_keras_model(self):
        input_ = layers.Input(shape=(self.input_dims_,))
        #model = layers.noise.GaussianNoise(0.005)(input_)
        model = layers.Dense(256, kernel_initializer='Orthogonal')(input_)
        model = layers.Activation('selu')(model)
        #model = layers.noise.AlphaDropout(0.1, seed=1)(model)
        #model = layers.BatchNormalization()(model)
        #model = layers.advanced_activations.PReLU()(model)
        #model = layers.Dropout(0.2)(model)

        model = layers.Dense(64, kernel_initializer='Orthogonal')(model)
        model = layers.Activation('selu')(model)
        #model = layers.noise.AlphaDropout(0.1, seed=1)(model)
        #model = layers.BatchNormalization()(model)
        #model = layers.advanced_activations.PReLU()(model)
        #model = layers.Dropout(0.4)(model)

        model = layers.Dense(16, kernel_initializer='Orthogonal')(model)
        #model = layers.BatchNormalization()(model)
        #model = layers.advanced_activations.PReLU()(model)
        model = layers.Activation('selu')(model)

        model = layers.Dense(1, activation='sigmoid')(model)

        model = models.Model(input_, model)
        model.compile(loss = 'binary_crossentropy', optimizer = optimizers.Nadam())
        #print(model.summary(line_length=120))
        return model

def predict():
    return model().predict()

if '__main__' == __name__:
    m = model()
    print('starting', m.now())
    m.main()
    print('done.', m.now())
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import gc

import numpy as np
import pandas as pd

from sklearn import metrics
from sklearn import model_selection
from sklearn import preprocessing

import state
debug_mode = False
public_score = None
state = state.State('l1_3_keras_2')
import data_clean_2 as data
import features_text_2 as fea_1

def tf_force_cpu(f):
    def ff(*args, **kwargs):
        import tensorflow as tf
        with tf.device('/cpu:0'):
            return f(*args, **kwargs)
    return ff

def build_keras_fit_callbacks(model_path):
    from keras import callbacks
    return [
           callbacks.EarlyStopping(
                  monitor='val_loss',
                  patience=20
                  #verbose=1
                   ),
           callbacks.ModelCheckpoint(
                  model_path,
                  monitor='val_loss',
                  save_best_only=True,
                  save_weights_only=True,
                  verbose=0
                   ),
           callbacks.ReduceLROnPlateau(
                  monitor='val_loss',
                  min_lr=1e-7,
                  factor=0.2,
                  verbose=0
                   )
           ]

def keras_limit_mem():
    from keras import backend as K
    K.get_session().close()
    cfg = K.tf.ConfigProto()
    cfg.gpu_options.allow_growth = True
    K.set_session(K.tf.Session(config=cfg))#@tf_force_cpu

def run(train, y, test, v, z):
    #cname = sys._getframe().f_code.co_name
    from keras import layers
    from keras import models
    from keras import optimizers
    cname = 'p'
    train.drop('id', axis=1, inplace=True)
    test.drop('id', axis=1, inplace=True)
    num_splits = 9
    scaler = preprocessing.RobustScaler()
    train = scaler.fit_transform(train)
    test = scaler.transform(test)
    input_dims = train.shape[1]
    def build_model():
        input_ = layers.Input(shape=(input_dims,))
        model = layers.Dense(512, kernel_initializer='Orthogonal')(input_)
        #model = layers.BatchNormalization()(model)
        #model = layers.advanced_activations.PReLU()(model)
        model = layers.Activation('selu')(model)
        #model = layers.Dropout(0.7)(model)

        model = layers.Dense(256, kernel_initializer='Orthogonal')(model)
        #model = layers.BatchNormalization()(model)
        model = layers.Activation('selu')(model)
        #model = layers.advanced_activations.PReLU()(model)
        #model = layers.Dropout(0.9)(model)

        model = layers.Dense(256, kernel_initializer='Orthogonal')(model)
        model = layers.BatchNormalization()(model)
        model = layers.Activation('selu')(model)
        #model = layers.advanced_activations.PReLU()(model)
        #model = layers.Dropout(0.9)(model)

        model = layers.Dense(16, kernel_initializer='Orthogonal')(model)
        #model = layers.BatchNormalization()(model)
        model = layers.Activation('selu')(model)
        #model = layers.advanced_activations.PReLU()(model)

        model = layers.Dense(1, activation='sigmoid')(model)

        model = models.Model(input_, model)
        model.compile(loss = 'binary_crossentropy', optimizer = optimizers.Nadam())
        #print(model.summary(line_length=120))
        return model
    batch_size = 128
    np.random.seed(1234)
    build_model().summary(line_length=120)
    ss = model_selection.ShuffleSplit(n_splits=num_splits, random_state=11, test_size=1/num_splits)
    scores = list()
    model_path = state.temp_name('keras_mlp_weights')
    v[cname] = 0
    z[cname] = 0
    for n, (itrain, ival) in enumerate(ss.split(train, y)):
        xtrain, xval = train[itrain], train[ival]
        ytrain, yval = y[itrain], y[ival]
        model = build_model()
        model.fit(
                xtrain, ytrain,
                batch_size = batch_size,
                epochs = 10000,
                validation_data = (xval, yval),
                verbose = 0,
                callbacks = build_keras_fit_callbacks(model_path),
                shuffle = True
            )
        model.load_weights(model_path)
        p = model.predict(xval)
        v.loc[ival, cname] += p.ravel()
        score = metrics.log_loss(y[ival], p)
        print(cname, 'fold %d: '%(n+1), score, state.now())
        scores.append(score)
        z[cname] += model.predict(test).ravel()
        del model
        for i in range(3): gc.collect(i)
    print('scores:', scores, np.mean(scores), np.std(scores))
    state.drop_temp(model_path)
    cv=np.mean(scores)
    z[cname] /= num_splits
    z['y'] = z[cname]

    return cv, None

def predict():
    saved = state.load('model')
    if debug_mode:
        saved = None
    if saved == None:
        train, y, test, _ = data.get()
        ftrain, ftest, _ = fea_1.get()
        train = pd.concat([train, ftrain], axis=1)
        test = pd.concat([test, ftest], axis=1)
        print(train.shape, test.shape)

        z = pd.DataFrame()
        z['id'] = test.id
        z['y'] = 0

        v = pd.DataFrame()
        v['id'] = train.id
        v['y'] = y
        cv, _ = run(train.astype('float32'), y, test.astype('float32'), v, z)
        state.save('model', (v, z, cv, None))
    else:
        v, z, cv, _ = saved
    return v, z, cv, _

if '__main__' == __name__:
    print('starting', state.now())
    state.run_predict(predict, debug_mode, public_score)
    print('done.', state.now())

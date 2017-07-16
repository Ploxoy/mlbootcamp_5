#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jun 15 20:26:49 2017

@author: user
"""
import datetime
import os
import sys

import matplotlib.pyplot as plot
import numpy as np
import pandas as pd
import seaborn as sns
import xgboost as xgb

from sklearn import ensemble
from sklearn import metrics
from sklearn import model_selection
from sklearn import preprocessing

from keras import backend as K
from keras import callbacks
from keras import layers
from keras import models
from keras import optimizers
from keras.wrappers.scikit_learn import KerasRegressor

def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def csv_name_suffix():
    script_name = os.path.basename(sys.argv[0])
    script_name = script_name[script_name.index('_'):-3]
    return script_name + '.csv'

def cleanup(train, test, use_hand_labels = False):
    '''
    train.ix[train.ap_hi < 0, 'ap_hi'] *= -1
    train.ix[train.ap_hi < 50, 'ap_hi'] *= 10
    train.ix[train.ap_hi > 5000, 'ap_hi'] *= 1e-2
    train.ix[train.ap_hi > 500, 'ap_hi'] *= 1e-1

    if use_hand_labels:
        test.ix[1929, ['ap_hi', 'ap_lo']] = 110, 99
        test.ix[15510, ['ap_hi', 'ap_lo']] = 120, 88
        test.ix[12852, ['ap_hi', 'ap_lo']] = 130, np.NaN

    test.ix[test.ap_hi < 0, 'ap_hi'] *= -1
    test.ix[(test.ap_hi < 25).values, 'ap_hi'] *= 10
    test.ix[test.ap_hi > 5000, 'ap_hi'] *= 1e-2
    test.ix[test.ap_hi > 500, 'ap_hi'] *= 1e-1

    if use_hand_labels:
        train.ix[8757, ['ap_hi', 'ap_lo']] = 120, 88
        train.ix[2014, ['ap_hi', 'ap_lo']] = 90, 60
        train.ix[17381, ['ap_hi', 'ap_lo']] = 130, 80
        train.ix[31783, ['ap_hi', 'ap_lo']] = 90, 70
        train.ix[38370, ['ap_hi', 'ap_lo']] = 140, 80
        train.ix[41505, ['ap_hi', 'ap_lo']] = 80, 60
        train.ix[42397, ['ap_hi', 'ap_lo']] = 90, 60
        train.ix[43922, ['ap_hi', 'ap_lo']] = 100, 80
        train.ix[63787, ['ap_hi', 'ap_lo']] = 110, 70
        train.ix[68663, ['ap_hi', 'ap_lo']] = 90, 60

    train.ix[train.ap_lo < 0, 'ap_lo'] *= -1
    train.ix[train.ap_lo > 2500, 'ap_lo'] *= 1e-2
    train.ix[train.ap_lo > 250, 'ap_lo'] *= 1e-1
    train.ix[train.ap_lo < 10, 'ap_lo'] *= 10
    train.ix[train.ap_lo < 10, 'ap_lo'] = np.NAN
    train.ix[(train.ap_lo < 49).values * (train.cardio==0).values, 'ap_lo'] = np.NAN

    test.ix[test.ap_lo < 0, 'ap_lo'] *= -1
    test.ix[test.ap_lo > 2500, 'ap_lo'] *= 1e-2
    test.ix[test.ap_lo > 250, 'ap_lo'] *= 1e-1
    test.ix[test.ap_lo < 10, 'ap_lo'] *= 10

    train.ix[train.height < 90, 'height'] += 100
    test.ix[test.height < 90, 'height'] += 100
    #'''

    temp = pd.DataFrame()
    temp['ap_hi'] = np.maximum(train.ap_hi, train.ap_lo)
    temp['ap_lo'] = np.minimum(train.ap_hi, train.ap_lo)
    train.ap_hi = temp.ap_hi
    train.ap_lo = temp.ap_lo

    temp = pd.DataFrame()
    temp['ap_hi'] = np.maximum(test.ap_hi, test.ap_lo)
    temp['ap_lo'] = np.minimum(test.ap_hi, test.ap_lo)
    test.ap_hi = temp.ap_hi
    test.ap_lo = temp.ap_lo

    for c in ['active', 'alco', 'smoke']:
        test.ix[test[c]=='None', c] = test[c][test[c]!= 'None'].astype('int32').mean()
        test[c] = test[c].astype('float32')

    return train, test

def gen_features(train, y, test):
    ntrain = len(train)
    df_all = pd.concat([train, test])

    df_all['ap_diff'] = df_all.ap_hi - df_all.ap_lo

    df_all['BWI'] = df_all.weight / (df_all.height / 100) / (df_all.height / 100)
    df_all['bad_bwi'] = (df_all.BWI > 60).values * 1 + (df_all.BWI < 10).values * 1

    df_all['bad_height'] = (df_all.height < 130).values * 1

    df_all['bad_weight'] = (df_all.weight + 120 < df_all.height).values * 1

    df_all['bad_ap_hi'] = 0
    df_all.ix[(df_all.ap_hi < 80).values + (df_all.ap_hi > 220).values, 'bad_ap_hi'] = 1

    df_all['bad_ap_lo'] = 0
    df_all.ix[(df_all.ap_lo < 40).values + (df_all.ap_lo > 200).values, 'bad_ap_lo'] = 1

    df_all['has_bad_data'] = (df_all.bad_bwi + df_all.bad_height + df_all.bad_weight + df_all.bad_ap_hi + df_all.bad_ap_lo) > 0

    df_all['w_div_h'] = df_all.weight / df_all.height
    df_all['h_sub_w'] = df_all.height - df_all.weight
    df_all['ap_hi_sub_w'] = df_all.ap_hi - df_all.weight

    df_all['age_months'] = df_all.age // 30
    df_all['age_years'] = df_all.age // 365

    return df_all[:ntrain].reindex(), y, df_all[ntrain:].reindex()

def keras1(train2, y, test2, v, z):
    cname = sys._getframe().f_code.co_name
    v[cname], z[cname] = 0, 0
    scores = list()
    scaler = preprocessing.RobustScaler()
    train3 = scaler.fit_transform(train2)
    test3 = scaler.transform(test2)
    input_dims = train3.shape[1]
    def build_model():
        input_ = layers.Input(shape=(input_dims,))
        model = layers.Dense(int(input_dims * 7.33),
                             kernel_initializer='Orthogonal',
                             activation=layers.advanced_activations.PReLU())(input_)
        model = layers.BatchNormalization()(model)
        #model = layers.Dropout(0.7)(model)
        model = layers.Dense(int(input_dims * 4.35),
                             kernel_initializer='Orthogonal',
                             activation=layers.advanced_activations.PReLU())(model)
        model = layers.BatchNormalization()(model)
        #model = layers.Dropout(0.9)(model)
        model = layers.Dense(int(input_dims * 0.51),
                             kernel_initializer='Orthogonal',
                             activation=layers.advanced_activations.PReLU())(model)
        model = layers.BatchNormalization()(model)
        model = layers.Dense(1,
                             activation='sigmoid')(model)
        model = models.Model(input_, model)
        model.compile(loss = 'binary_crossentropy',
                      optimizer = optimizers.Nadam(),
                      metrics=["accuracy"])
        #print(model.summary(line_length=120))
        return model
    np.random.seed(1234)
    est = KerasRegressor(build_fn=build_model,
                         nb_epoch=10000,
                         batch_size=128,
                         #verbose=2
                        )
    model_path = '../data/working/' + csv_name_suffix()
    model_path = model_path[:-7] + '_keras_model.h5'
    kcb = [
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
                  verbose=1
                   )
           ]
    num_splits = 5
    ss = model_selection.ShuffleSplit(n_splits=num_splits, random_state=11)
    for n, (itrain, ival) in enumerate(ss.split(train3, y)):
        xtrain, xval = train3[itrain], train3[ival]
        ytrain, yval = y[itrain], y[ival]
        est.fit(
                xtrain, ytrain,
                epochs=10000,
                validation_data=(xval, yval),
                verbose=0,
                callbacks=kcb,
                shuffle=True
            )
        est.model.load_weights(model_path)
        p = est.predict(xval)
        v.loc[ival, cname] += p
        score = metrics.log_loss(y[ival], p)
        print(cname, 'fold %d: '%(n+1), score, now())
        scores.append(score)
        z[cname] += est.predict(test3)
    os.remove(model_path)
    print(est.model.summary(line_length=120))

    cv=np.array(scores)
    print(cv, cv.mean(), cv.std())
    z[cname] /= num_splits

def xgb1(train2, y, test2, v, z):
    cname = sys._getframe().f_code.co_name
    v[cname], z[cname] = 0, 0
    N_splits = 5
    scores = []
    skf = model_selection.StratifiedKFold(n_splits=N_splits, shuffle=True)
    xgb_params = dict(
            max_depth = 4,
            learning_rate = 0.01,
            objective = 'binary:logistic',
            eval_metric = 'logloss',
            seed = 1,
            silent = 1
        )
    for n, (itrain, ival) in enumerate(skf.split(train2, y)):
        print('step %d of %d'%(n+1, skf.n_splits), now())
        dtrain = xgb.DMatrix(train2.ix[itrain], y[itrain])
        dvalid = xgb.DMatrix(train2.ix[ival], y[ival])
        dtest = xgb.DMatrix(test2)
        watch = [(dtrain, 'train'), (dvalid, 'valid')]
        clf = xgb.train(xgb_params, dtrain, 10000, watch, early_stopping_rounds=100, verbose_eval=1000)

        p = clf.predict(dvalid)
        v.loc[ival, cname] += p
        score = metrics.log_loss(y[ival], p)
        z[cname]  += np.log1p(clf.predict(dtest))
        print(cname, 'seed %d step %d: '%(xgb_params['seed'], n+1), score, now())
        scores.append(score)

    print('validation loss: ', metrics.log_loss(y, v[cname]))
    cv=np.array(scores)
    print(cv, cv.mean(), cv.std())
    z[cname] /= N_splits

def xgb2(train2, y, test2, v, z):
    cname = sys._getframe().f_code.co_name
    v[cname], z[cname] = 0, 0
    N_splits = 5
    scores = []
    skf = model_selection.StratifiedKFold(n_splits=N_splits, shuffle=True)
    xgb_params = dict(
            max_depth = 3,
            learning_rate = 0.01,
            subsample = 0.7,
            #colsample_bytree = 0.8,
            objective = 'binary:logistic',
            eval_metric = 'logloss',
            seed = 1,
            silent = 1
        )
    dtest = xgb.DMatrix(test2)
    for n, (itrain, ival) in enumerate(skf.split(train2, y)):
        print('step %d of %d'%(n+1, skf.n_splits), now())
        dtrain = xgb.DMatrix(train2.ix[itrain], y[itrain])
        dvalid = xgb.DMatrix(train2.ix[ival], y[ival])
        watch = [(dtrain, 'train'), (dvalid, 'valid')]
        clf = xgb.train(xgb_params, dtrain, 10000, watch, early_stopping_rounds=100, verbose_eval=1000)

        p = clf.predict(dvalid)
        v.loc[ival, cname] += p
        score = metrics.log_loss(y[ival], p)
        z[cname]  += np.log1p(clf.predict(dtest))
        print(cname, 'seed %d step %d: '%(xgb_params['seed'], n+1), score, now())
        scores.append(score)

    print('validation loss: ', metrics.log_loss(y, v[cname]))
    cv=np.array(scores)
    print(cv, cv.mean(), cv.std())
    z[cname] /= N_splits

def save_results(v, z):
    pred_path = '../submissions/p' + csv_name_suffix()
    all_data_path = '../data/output/model' + csv_name_suffix()

    z[['y']].to_csv(pred_path, header=None, index=False)
    print(z.head(20))

    v['train'] = 1
    z['train'] = 0

    q = pd.concat([v, z], axis=0)
    q.to_csv(all_data_path, index=False, compression='gzip')
    print('saved', pred_path, all_data_path)

if '__main__' == __name__:
    print('starting', now())
    np.random.seed(1234)

    train = pd.read_csv('../data/input/train.csv', delimiter=';')
    test = pd.read_csv('../data/input/test.csv', delimiter=';')

    train, test = cleanup(train, test)

    y = train.cardio
    train.drop('cardio', axis=1, inplace=True)

    z = pd.DataFrame()
    z['id'] = test.id
    z['y'] = 0

    v = pd.DataFrame()
    v['y'] = y

    train2, y, test2 = gen_features(train, y, test)

    keras1(train2, y, test2, v, z)
    xgb1(train2, y, test2, v, z)
    xgb2(train2, y, test2, v, z)

    z.y = np.expm1(z.xgb1 * 0.4 + z.xgb2 * 0.4 + z.keras1 * 0.2)
    save_results(v, z)

    print('done: %s.'%(now()))

    #'''
    clf = xgb.XGBClassifier(n_estimators=1000, learning_rate=.005)
    clf.fit(train2, y)
    for c in ['weight', 'gain', 'cover']:
        xgb.plot_importance(clf, title = 'Feature ' + c, importance_type=c)
    #'''
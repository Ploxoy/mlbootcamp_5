#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import xgboost as xgb

from sklearn import metrics
from sklearn import model_selection

import state
public_score = None
debug_mode = False
state = state.State('l1_4_xgb_1')
import data_clean_2 as data
import features_text_1 as fea_1
import features_misc_1 as fea_2

def run(train, y, test, v, z):
    #cname = sys._getframe().f_code.co_name
    cname = 'p'
    train.drop('id', axis=1, inplace=True)
    test.drop('id', axis=1, inplace=True)
    from hyperopt import fmin, tpe, hp, STATUS_OK, Trials, space_eval
    dtrain = xgb.DMatrix(train, y)
    def step_xgb(params):
        cv = xgb.cv(params=params,
                    dtrain=dtrain,
                    num_boost_round=10000,
                    early_stopping_rounds=50,
                    nfold=10,
                    seed=params['seed'])
        score = cv.ix[len(cv)-1, 0]
        print(cname, score, len(cv), params)
        return dict(loss=score, status=STATUS_OK)
    space_xgb = dict(
            max_depth = hp.choice('max_depth', range(2, 9)),
            subsample = hp.quniform('subsample', 0.6, 1, 0.05),
            colsample_bytree = hp.quniform('colsample_bytree', 0.6, 1, 0.05),
            learning_rate = hp.quniform('learning_rate', 0.005, 0.1, 0.005),
            min_child_weight = hp.quniform('min_child_weight', 1, 6, 1),
            gamma = hp.quniform('gamma', 0.5, 10, 0.05),
            reg_alpha = hp.quniform('reg_alpha', 0, 1, 0.001),

            objective = 'binary:logistic',
            eval_metric = 'logloss',
            seed = 1,
            silent = 1
        )
    trs = state.load('xgb_trials')
    if trs == None or debug_mode:
        tr = Trials()
    else:
        tr, _ = trs
    if len(tr.trials) > 0:
        print('reusing %d trials, best was:'%(len(tr.trials)), space_eval(space_xgb, tr.argmin))
        best = tr.argmin
    while len(tr.trials) < 15:
        best = fmin(step_xgb, space_xgb, algo=tpe.suggest, max_evals=len(tr.trials) + 1, trials = tr)
        state.save('xgb_trials', (tr, space_xgb))
    xgb_params = space_eval(space_xgb, best)
    print(xgb_params)

    N_splits = 9
    N_seeds = 3

    skf = model_selection.StratifiedKFold(n_splits=N_splits, shuffle=True)
    dtest = xgb.DMatrix(test)
    cv = []
    for s in range(N_seeds):
        scores = []
        cname2 = cname + str(s)
        v[cname2], z[cname2] = 0, 0
        xgb_params['seed'] = s + 4242
        for n, (itrain, ival) in enumerate(skf.split(train, y)):
            dtrain = xgb.DMatrix(train.ix[itrain], y[itrain])
            dvalid = xgb.DMatrix(train.ix[ival], y[ival])
            watch = [(dtrain, 'train'), (dvalid, 'valid')]
            clf = xgb.train(xgb_params, dtrain, 10000, watch, early_stopping_rounds=100, verbose_eval=False)

            p = clf.predict(dvalid)
            v.loc[ival, cname2] += p
            score = metrics.log_loss(y[ival], p)
            z[cname2]  += clf.predict(dtest)
            print(cname, 'seed %d step %d of %d: '%(xgb_params['seed'], n+1, skf.n_splits), score, state.now())
            scores.append(score)
        z[cname2] /= N_splits
        cv.append(np.mean(scores))
        print('seed %d loss: '%(xgb_params['seed']), scores, np.mean(scores), np.std(scores))
        z['y'] = z[cname2]

    print('cv:', cv, np.mean(cv), np.std(cv))
    return cv, None

def predict():
    saved = state.load('model')
    #saved = None
    if debug_mode:
        saved = None
    if saved == None:
        train, y, test, _ = data.get()
        ftrain, ftest, _ = fea_1.get()
        ftrain2, ftest2, _ = fea_2.get()
        train = pd.concat([train, ftrain, ftrain2], axis=1)
        test = pd.concat([test, ftest, ftest2], axis=1)
        print(train.shape, test.shape)

        z = pd.DataFrame()
        z['id'] = test.id
        z['y'] = 0

        v = pd.DataFrame()
        v['id'] = train.id
        v['y'] = y
        cv, _ = run(train, y, test, v, z)
        state.save('model', (v, z, cv, None))
    else:
        v, z, cv, _ = saved
    return v, z, cv, _

if '__main__' == __name__:
    print('starting', state.now())
    state.run_predict(predict, debug_mode, public_score)
    print('done.', state.now())

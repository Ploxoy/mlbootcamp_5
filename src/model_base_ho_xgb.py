#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import xgboost as xgb

from sklearn import metrics
from sklearn import model_selection

from functools import partial

import model_base

class XgbModelBase(model_base.Model):
    def __init__(self,
                 name,
                 data_source,
                 features=[],
                 debug=False,
                 public_score=None,
                 max_ho_trials = 30,
                 num_splits = 9,
                 num_seeds = 3,
                 base_seed = 4242):
        super().__init__(name, data_source,features, debug, public_score)
        self.num_splits_ = num_splits
        self.num_seeds_ = num_seeds
        self.base_seed_ = base_seed
        self.max_ho_trials_ = max_ho_trials

    def model(self):
        #cname = sys._getframe().f_code.co_name
        cname = 'xgb'
        train, y, test = self.train_, self.y_, self.test_
        train.drop('id', axis=1, inplace=True)
        test.drop('id', axis=1, inplace=True)
        from hyperopt import fmin, tpe, hp, STATUS_OK, Trials, space_eval
        dtrain = xgb.DMatrix(train, y)
        def step_xgb(params):
            cv = xgb.cv(params=params,
                        dtrain=dtrain,
                        num_boost_round=10000,
                        early_stopping_rounds=50,
                        nfold=6,
                        seed=params['seed'])
            score = cv.ix[len(cv)-1, 0]
            print(cname, score, len(cv), params, self.now())
            return dict(loss=score, status=STATUS_OK)
        space_xgb = dict(
                max_depth = hp.choice('max_depth', range(2, 9)),
                subsample = hp.quniform('subsample', 0.6, 1, 0.05),
                colsample_bytree = hp.quniform('colsample_bytree', 0.6, 1, 0.05),
                learning_rate = hp.quniform('learning_rate', 0.005, 0.1, 0.005),
                min_child_weight = hp.quniform('min_child_weight', 1, 6, 1),
                gamma = hp.choice('gamma', [0, hp.quniform('gamma2', 0, 10, 0.05)]),
                reg_alpha = hp.quniform('reg_alpha', 0, 1, 0.001),

                objective = 'binary:logistic',
                eval_metric = 'logloss',
                seed = 1,
                silent = 1,
            )
        trs = self.load('xgb_trials')
        if trs == None or self.debug_:
            tr = Trials()
        else:
            tr, _ = trs
        if len(tr.trials) > 0:
            print('reusing %d trials, best was:'%(len(tr.trials)), space_eval(space_xgb, tr.argmin))
            best = tr.argmin
        while len(tr.trials) < self.max_ho_trials_:
            print(len(tr.trials), end=' ')
            best = fmin(step_xgb, space_xgb, algo=partial(tpe.suggest, n_startup_jobs=1), max_evals=len(tr.trials) + 1, trials = tr)
            self.save('xgb_trials', (tr, space_xgb))
        xgb_params = space_eval(space_xgb, best)
        print(xgb_params)

        N_splits = self.num_splits_
        N_seeds = self.num_seeds_

        v, z = self.v_, self.z_
        skf = model_selection.StratifiedKFold(n_splits=N_splits, shuffle=True)
        dtest = xgb.DMatrix(test)
        cv = []
        for s in range(N_seeds):
            scores = []
            cname2 = cname + str(s)
            v[cname2], z[cname2] = 0, 0
            xgb_params['seed'] = s + self.base_seed_
            for n, (itrain, ival) in enumerate(skf.split(train, y)):
                dtrain = xgb.DMatrix(train.ix[itrain], y[itrain])
                dvalid = xgb.DMatrix(train.ix[ival], y[ival])
                watch = [(dtrain, 'train'), (dvalid, 'valid')]
                clf = xgb.train(xgb_params, dtrain, 10000, watch, early_stopping_rounds=100, verbose_eval=False)

                p = clf.predict(dvalid)
                v.loc[ival, cname2] += p
                score = metrics.log_loss(y[ival], p)
                z[cname2]  += clf.predict(dtest)
                print(cname, 'seed %d step %d of %d: '%(xgb_params['seed'], n+1, skf.n_splits), score, self.now())
                scores.append(score)
            z[cname2] /= N_splits
            cv.append(np.mean(scores))
            print('seed %d loss: '%(xgb_params['seed']), scores, np.mean(scores), np.std(scores))
            z['y'] = z[cname2]

        print('cv:', cv, np.mean(cv), np.std(cv))
        return cv, None

if '__main__' == __name__:
    pass
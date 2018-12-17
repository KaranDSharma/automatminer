from __future__ import unicode_literals
import logging
import numpy
import keras.models
import keras.legacy.layers
import keras.regularizers
import sklearn.metrics
import sklearn.base
import keras.constraints
import keras.layers.noise
import keras.optimizers
import keras.callbacks
from sklearn.datasets import load_boston
from sklearn.model_selection import train_test_split
from keras.wrappers.scikit_learn import KerasRegressor, KerasClassifier
import pandas as pd

_classifier_modes = {'classifier', 'classification', 'classify'}

_regressor_modes = {'regressor', 'regression', 'regress'}

class NnWrapper(sklearn.base.BaseEstimator, sklearn.base.RegressorMixin, sklearn.base.ClassifierMixin):
    """Wrapper for Keras feed-forward neural network for classification to enable scikit-learn grid search"""
    def __init__(self, hidden_layer_sizes=(100,), dropout=0.5, show_accuracy=True, batch_spec=((400, 1024), (100, -1)), activation="sigmoid", input_noise=0., use_maxout=False, use_maxnorm=False, learning_rate=0.001, stop_early=False, type="regression"):
        self.hidden_layer_sizes = hidden_layer_sizes
        self.dropout = dropout
        self.show_accuracy = show_accuracy
        self.batch_spec = batch_spec
        self.activation = activation
        self.input_noise = input_noise
        self.use_maxout = use_maxout
        self.use_maxnorm = use_maxnorm
        self.learning_rate = learning_rate
        self.stop_early = stop_early

        if self.use_maxout:
            self.use_maxnorm = True

        self.model_ = None
        self.estimator = None
        self.classifier = None
        if type in _classifier_modes:
            self.type = "classification"
        else:
            self.type = "regression"

    def getModel(self):
        return self.model_

    def fit(self, X, y, **kwargs):
        self.set_params(**kwargs)
        model = keras.models.Sequential()
        first = True
        if self.input_noise > 0:
            model.add(keras.layers.GaussianNoise(self.input_noise, input_shape=X.shape[1:]))
        num_maxout_features = 2
        dense_kwargs = {"init": "glorot_uniform"}
        if self.use_maxnorm:
            dense_kwargs["W_constraint"] = keras.constraints.maxnorm(2)

        # hidden layers
        for layer_size in self.hidden_layer_sizes:
            if first:
                if self.use_maxout:
                    model.add(keras.legacy.layers.MaxoutDense(output_dim=layer_size / num_maxout_features,
                                                                input_dim=X.shape[1], init="glorot_uniform",
                                                                nb_feature=num_maxout_features))
                else:
                    model.add(keras.layers.Dense(units=layer_size, input_dim=X.shape[1], kernel_initializer="glorot_uniform"))
                    model.add(keras.layers.Activation(self.activation))
                    first = False
            else:
                if self.use_maxout:
                    model.add(keras.legacy.layers.MaxoutDense(output_dim=layer_size / num_maxout_features,
                                                                init="glorot_uniform",
                                                                nb_feature=num_maxout_features))
                else:
                    model.add(keras.layers.Dense(units=layer_size, kernel_initializer="glorot_uniform"))
                    model.add(keras.layers.Activation(self.activation))
            model.add(keras.layers.Dropout(self.dropout))

        if first:
            model.add(keras.layers.Dense(output_dim=1, input_dim=X.shape[1], **dense_kwargs))
        else:
            model.add(keras.layers.Dense(units=1, kernel_initializer="glorot_uniform"))
        model.add(keras.layers.Activation(self.activation))

        optimizer = keras.optimizers.Adam(lr=self.learning_rate, beta_1=0.9, beta_2=0.999, epsilon=1e-8)
        if self.type == "classification":
            model.compile(loss="binary_crossentropy", optimizer="adamax")
        else:
            model.compile(loss="mse", optimizer=optimizer)

        # batches as per configuration
        for num_iterations, batch_size in self.batch_spec:
            callbacks = None
            validation_split = 0.0
            if self.stop_early and batch_size > 0:
                callbacks = [EarlyStopping(monitor='val_loss', patience=20, verbose=1)]
                validation_split = 0.2

            if batch_size < 0:
                batch_size = X.shape[0]
            if num_iterations > 0:
                model.fit(X, y, epochs=num_iterations, batch_size=batch_size, verbose=self.show_accuracy,
                              callbacks = callbacks, validation_split = validation_split)

        if self.stop_early:
            # final refit with full data
            model.fit(X, y, nb_epoch=5, batch_size=X.shape[0], show_accuracy=self.show_accuracy)

        self.model_ = model
        if self.type == "regression":
            self.estimator = KerasRegressor(build_fn=self.getModel, epochs=self.batch_spec[0][0], batch_size=self.batch_spec[0][1], verbose=0)
            self.estimator.fit(X, y)
        else:
            self.classifier = KerasClassifier(build_fn=self.getModel, epochs=self.batch_spec[0][0], batch_size=self.batch_spec[0][1], verbose=0)
            self.classifier.fit(X, y)

    def predict(self, X):
        if self.type == "classification":
            return self.classifier.predict(X)
        else:
            return self.estimator.predict(X)

    def predict_proba(self, X):
        if self.type == "classification":
            return self.classifier.predict_proba(X)
        else:
            return self.estimator.predict(X)

    def score(self, X, y):
        #Set score for regression and classify
        if self.type == "classification":
            return sklearn.metrics.accuracy_score(y, self.predict(X))
        else:
            return sklearn.metrics.r2_score(y, self.predict(X))

if __name__ == "__main__":
    wrapper = NnWrapper(input_noise=1.0)
    boston = load_boston()
    bos = pd.DataFrame(boston.data)
    bos.columns = boston.feature_names
    bos['PRICE'] = boston.target
    print(bos)
    X_train, X_test, y_train, y_test = train_test_split(bos.drop(columns="PRICE"), bos["PRICE"], test_size=0.33, random_state=42)
    wrapper.fit(X_train, y_train)
    d = pd.DataFrame()
    print(wrapper.predict_proba(X_test))
    print(y_test)
    print(wrapper.score(X_test, y_test))
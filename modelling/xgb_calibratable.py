from xgboost import XGBClassifier


class XGBClassifierCalibratable(XGBClassifier):
    """XGBoost's sklearn wrapper doesn't expose `decision_function`, so
    scikit-learn's CalibratedClassifierCV falls back to its binary
    `predict_proba` path, which (as of xgboost 2.0.x / scikit-learn 1.9)
    mishandles the label-binarized target and raises an IndexError. Adding
    the margin-score `decision_function` routes it through the working
    code path instead - purely a compatibility shim, same underlying model.

    Lives in its own module (rather than train_models.py) so that joblib
    pickles it under a stable, importable path (`modelling.xgb_calibratable`)
    instead of `__main__` - `__main__` refers to whatever script happens to be
    the entry point at unpickling time (e.g. pytest's own __main__), which
    doesn't define this class and breaks `joblib.load`.
    """

    def decision_function(self, X):
        return self.predict(X, output_margin=True)

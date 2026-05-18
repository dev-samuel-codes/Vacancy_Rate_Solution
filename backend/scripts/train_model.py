# 모델 학습해서 저장

import keras

import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier

data = pd.read_csv("backend/data/survival_model_dataset.csv")
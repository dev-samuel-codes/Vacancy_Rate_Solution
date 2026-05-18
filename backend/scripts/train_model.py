import keras

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier

#파일 불러오기
data = pd.read_csv("backend/data/survival_model_dataset.csv")

#특성값과 타깃값 설정
target_column = "target_survived_over_1_year"

x = data.drop(columns=[target_column])
y = data[target_column]

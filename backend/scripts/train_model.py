import keras

import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier

# 파일 불러오기
data = pd.read_csv("backend/data/survival_model_dataset.csv")

# 사용하지 않을 데이터 제거
data = data.drop(columns=["period", "region"])

# 문자열 범주형 데이터를 더미 변수로 변환
data = pd.get_dummies(
    data,
    columns = ["district", "business_type"],
    dtype = int
)

# 특성값과 타깃값 설정
target_column = "target_survived_over_1_year"

x = data.drop(columns=[target_column])
y = data[target_column]

# 훈련데이터와 테스트데이터 분리
x_train, x_test, y_train, y_test = train_test_split(x, y, stratify=y, test_size=0.2)
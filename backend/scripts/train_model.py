import joblib
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score


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
target_column = "vacancy_rate"

x = data.drop(columns=[target_column, "target_survived_over_1_year"])
y = data[target_column]

# 훈련데이터와 테스트데이터 분리
x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)
x_train, x_val, y_train, y_val = train_test_split(x_train, y_train, test_size=0.2, random_state=42)

# 공실률 예측 회귀 모델 학습
def vacancy_model(x_train, y_train, x_test, y_test, x_val, y_val, columns):
    model = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_iter=300,
        max_leaf_nodes=31,
        random_state=42
    )

    model.fit(x_train, y_train)

    train_pred = model.predict(x_train)
    val_pred = model.predict(x_val)
    test_pred = model.predict(x_test)

    plt.figure(figsize=(8, 6))

    plt.scatter(y_train, train_pred, alpha=0.2, label="Train")
    plt.scatter(y_val, val_pred, alpha=0.3, label="Validation")
    plt.scatter(y_test, test_pred, alpha=0.3, label="Test")

    min_value = min(y_train.min(), y_val.min(), y_test.min())
    max_value = max(y_train.max(), y_val.max(), y_test.max())

    plt.plot([min_value, max_value], [min_value, max_value], color="red")

    plt.xlabel("Actual Vacancy Rate")
    plt.ylabel("Predicted Vacancy Rate")
    plt.title("Actual vs Predicted Vacancy Rate")
    plt.legend()
    plt.show()
    
    print("검증 MAE:", mean_absolute_error(y_val, val_pred))
    print("검증 R2:", r2_score(y_val, val_pred))

    print("테스트 MAE:", mean_absolute_error(y_test, test_pred))
    print("테스트 R2:", r2_score(y_test, test_pred))

    # 학습 모델 저장
    joblib.dump(model, "backend/models/model.pkl")
    joblib.dump(
        {
            "columns": columns,
            "drop_columns": ["period", "region", "target_survived_over_1_year"],
            "categorical_columns": ["district", "business_type"],
            "target_column": "vacancy_rate"
        },
       "backend/models/preprocessor.pkl"
    )

vacancy_model(x_train, y_train, x_test, y_test, x_val, y_val, x.columns.tolist())

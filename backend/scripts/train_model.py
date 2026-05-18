import joblib
import pandas as pd

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
x_train, x_test, y_train, y_test = train_test_split(x, y, stratify=y, test_size=0.2, random_state=42)
x_train, x_val, y_train, y_val = train_test_split(x_train, y_train, stratify=y_train, test_size=0.2, random_state=42)

# 표준화
scaler = StandardScaler()
train_scaled = scaler.fit_transform(x_train)
val_scaled = scaler.transform(x_val)
test_scaled = scaler.transform(x_test)

# 로지스틱 회귀 모델
def logistic_model(train_scaled, y_train, val_scaled, y_val, test_scaled, y_test, scaler, columns):
    sc = SGDClassifier(loss='log_loss', random_state=42)
    sc.fit(train_scaled, y_train)
    print("훈련데이터 성능: ", sc.score(train_scaled, y_train))
    print("검증데이터 성능", sc.score(val_scaled, y_val))
    print("테스트데이터 성능: ", sc.score(test_scaled, y_test))

    # 모델 저장
    joblib.dump(sc, "backend/models/model.pkl")
    joblib.dump(
        {
            "scaler": scaler,
            "columns": columns
        },
        "backend/models/preprocessor.pkl"
    )

logistic_model(train_scaled, y_train, val_scaled, y_val, test_scaled, y_test, scaler, x.columns.tolist())
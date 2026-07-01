from collections import Counter
from pathlib import Path

from backend.evaluation.eval_lexical import load_dataset
from backend.integrations.nlp import lexical


from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support, classification_report
import json

from backend.integrations.nlp.linear import featurize_cues


def featurize(headline) -> list[int]:  # -> vector
    # Similar a Bag of Words, debemos contar cuanto hay de cada categoria léxica.
    result = lexical.detect(headline)  # "10 AMAZING Things You Won't Believe"

    categories_list = []
    for match in result.data["matches"]:
        categories_list.append(match["category"])

    # Matches = {category, cue, span} Usamos categorias

    contador = Counter(categories_list)
    vector = [contador[cat] for cat in lexical.CATEGORIES]
    return vector
    # Devuelve lista de int en orden de CATEGORIES


# En vez de modificar la anterior, dejo para que se puedan usar PATTERNS ya que sí es categórica, resto por cues y sumamos. (como una pveriosn avanzada)


if __name__ == "__main__":

    data = load_dataset()

    # Features: cleaning (MULTI_HOT)
    # Bag of Words Binario SIMPLIFICADO (por categoria en vez de palabra)

    headlines, labels = zip(*data)
    X = [featurize_cues(h) for h in headlines]
    y = labels

    # Split (Separamos train/test para evitar sesgo optimista -> sin generalización)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=24
    )

    model = LogisticRegression(
        max_iter=1000
    )  # LOGISITIC NO LINEAR PORQUE CLICKBAIT ES BINARIO (CONSTANTE), NO CONTINUO.

    # Era por debajo una combinacion lineal -> sigmoide -> [0,1]
    # 0.75 = 75% prob

    # Train (Pesos + error) Error sigue formula LOG-LOSS que penaliza fallar al afimrar clickbait
    model.fit(X_train, y_train)

    # Serializamos (podemos hacer sigmoide fuera para no depender de sklearn)
    feature_names = list(lexical.PATTERNS) + lexical.ALL_CUES

    linear_extract = {
        "weights": [float(w) for w in model.coef_[0]],  # np.float -> float
        "intercept": float(model.intercept_[0]),  # Sesgo (b),
        "feature_names": feature_names,
    }
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(linear_extract, f, sort_keys=True, ensure_ascii=False)

    # Predict (para x nuevo, aplicamos formula de antes)
    y_pred = model.predict(X_test)
    print(
        precision_recall_fscore_support(
            y_test, y_pred, average="binary", zero_division=0
        )
    )

    weight_table = sorted(
        zip(feature_names, model.coef_[0]),
        key=lambda par: par[1],
        reverse=True,
    )
    print("TABLA DE PESOS")
    print()
    print("TOP: ", weight_table[:20])
    print()
    print("BOTTOM: ", weight_table[-20:])

    # Lineal vs Reglas:
    rule_pred = []
    for x in X_test:
        if sum(x) >= lexical.THRESHOLD:
            rule_pred.append(1)
        else:
            rule_pred.append(0)

    print(
        "reglas",
        precision_recall_fscore_support(
            y_test, rule_pred, average="binary", zero_division=0
        ),
    )

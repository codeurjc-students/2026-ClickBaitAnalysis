from collections import Counter

from backend.evaluation.eval_lexical import load_dataset
from backend.integrations.nlp import lexical


from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support, classification_report


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


if __name__ == "__main__":

    data = load_dataset()

    # Features: cleaning (MULTI_HOT)
    # Bag of Words Binario SIMPLIFICADO (por categoria en vez de palabra)

    headlines, labels = zip(*data)
    X = [featurize(h) for h in headlines]
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

    # Predict (para x nuevo, aplicamos formula de antes)
    y_pred = model.predict(X_test)
    print(
        precision_recall_fscore_support(
            y_test, y_pred, average="binary", zero_division=0
        )
    )

    print(
        sorted(
            zip(lexical.CATEGORIES, model.coef_[0]),
            key=lambda par: par[1],
            reverse=True,
        )
    )

    # pista: sorted(zip(lexical.CATEGORIES, model.coef_[0]), key=..., reverse=True)

from flask import Flask, request, jsonify
import os
import torch
import torch.nn as nn
from transformers import DistilBertTokenizer, DistilBertModel

app = Flask(__name__)

class BertClassifier(nn.Module):
    def __init__(self, bert_model, num_classes, freeze_bert=False):
        super().__init__()
        self.bert = bert_model
        self.classifier = nn.Linear(self.bert.config.hidden_size, num_classes)
        if freeze_bert:
            for param in self.bert.parameters():
                param.requires_grad = False

    def forward(self, input_ids, attention_mask=None):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        cls_token = outputs.last_hidden_state[:, 0, :]
        logits = self.classifier(cls_token)
        return logits


# 🔥 WRAP DO CARREGAMENTO DO MODELO EM TRY/EXCEPT
try:
    device = torch.device("cpu")
    print(f"Usando dispositivo: {device}")

    tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')
    bert = DistilBertModel.from_pretrained("distilbert-base-uncased").to(device)

    model = BertClassifier(bert_model=bert, num_classes=2, freeze_bert=False).to(device)

    print("Carregando pesos...")
    model.load_state_dict(torch.load("modelo_classifica_commit(1).pth", map_location=device))

    model.eval()
    print("Modelo carregado com sucesso!")

except Exception as e:
    print("\n🔥 ERRO AO INICIAR O MODELO 🔥")
    print(e)
    raise e

def classify(message: str) -> bool:
    with torch.no_grad():
        encodings = tokenizer(message, truncation=True, padding=True, return_tensors='pt')
        input_ids = encodings['input_ids'].to(device)
        attention_mask = encodings['attention_mask'].to(device)
        
        logits = model(input_ids=input_ids, attention_mask=attention_mask)
        pred = torch.argmax(logits, dim=1).item()
        
        return pred == 1

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    commits = data.get("commits", [])

    for c in commits:
        msg = c["message"]
        result = classify(msg)

        print("\n----------------------------------")
        print("Commit:", c["id"])
        print("Mensagem:", msg)
        print("Status:", "APROVADO ✔️" if result else "REPROVADO ❌")
        print("----------------------------------")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)
    
    
##

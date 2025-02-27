from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from src.helper import download_hugging_face_embeddings
from langchain.vectorstores import Pinecone
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os
import logging
from flask_cors import CORS

# Initialize Flask app
app = Flask(__name__)
load_dotenv()
CORS(app)

#configure database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user_data.db'  # SQLite database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

#  Define the UserData model
class UserData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f'<UserData {self.phone}>'

# Create the database tables
with app.app_context():
    db.create_all()



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# PDF URLs
PDF_URLS = {
    "17k3k": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20221118_REFUdrive_RPCS-730-17K-17K3K_28K_datasheet_EN_V02.pdf",
    "cabinet": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20221118_REFUdrive-RPCS-630_datasheet_EN_V03.pdf",
    "dual_28k_55k": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20221118_REFUdrive_RPCS-730-2x28K-2x55K_850V_datasheet_EN_V02.pdf",
    "dual_15k_30k": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20221118_REFUdrive_RPCS-730-2x15K-2x30K_450V_datasheet_EN_V02.pdf",
    "traction_80k_160k": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20221124_REFUdrive_RPCS-730-80K-160K_450V_datasheet_EN_V03.pdf",
    "traction_150k_320k": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20221124_REFUdrive_RPCS-730-150K-320K_850V_datasheet_EN_V03.pdf",
    "traction_320k_hpp": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20221118_REFUdrive_RPCS-730-320K-HPP_datasheet_EN_V02.pdf",
    "dc_dc": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20241024_REFUdrive_RPCS-DC4K-900_6K-750_datasheet_EN_V02.pdf",
    "obc": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20230921_REFUdrive_22kW_On-Board_Charger_datasheet_EN_V11.pdf",
    "dual_17k": "https://www.refu-drive.com/fileadmin/user_upload/Downloads/Datenblaetter/EN/20241021_REFUdrive_RPCS-740-2x17K_datasheet_EN_V03.pdf"
}

# Initialize RAG components
PINECONE_API_KEY = os.environ.get('PINECONE_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Load embeddings
embeddings = download_hugging_face_embeddings()

# Initialize Pinecone vector store 
index_name = "refu"
docsearch = Pinecone.from_existing_index(index_name, embeddings)

# Create retriever
def create_filtered_retriever(button_path=None):
    source_mapping = {
        "inverter.aux_inverter.single_inverter.17kva": "Data\\Auxiliary inverter.single inerter.17k.pdf",
        "inverter.combi_inverter.17k3k": "Data\\combi inverter 17k3k.pdf",
        "inverter.aux_inverter.single_inverter.28kva": "Data\\Auxiliary inverter,single,28k.pdf",
        "inverter.aux_inverter.Dual_inverter.2x17kva": "Data\\Auxiliary inverter 2x17kva.pdf",
        "inverter.aux_inverter.Dual_inverter.2x15kva": "Data\\Auxiliary inverter 2x15kva.pdf",
        "inverter.aux_inverter.Dual_inverter.2x28kva": "Data\\Auxiliary inverter 2x28kva.pdf",
        "inverter.aux_inverter.Dual_inverter.2x30kva": "Data\\Auxiliary inverter 2x30kva.pdf",
        "inverter.aux_inverter.Dual_inverter.2x55kva": "Data\\Auxiliary inverter 2x55kva.pdf",
        "inverter.traction_inverter.80kva": "Data\\Traction inverter 80kva.pdf",
        "inverter.traction_inverter.160kva": "Data\\Traction inverter 160kva.pdf",
        "inverter.traction_inverter.150kva": "Data\\Traction inverter 150kva.pdf",
        "inverter.traction_inverter.320kva": "Data\\Traction inverter 320kva.pdf",
        "inverter.traction_inverter.320kva-HPP": "Data\\Traction inverter 320kva-HPP.pdf",
        "inverter.cabinet_inverter.8kva": "Data\\cabinet inverter 8kva.pdf",
        "inverter.cabinet_inverter.22kva": "Data\\cabinet inverter 22kva.pdf",
        "inverter.cabinet_inverter.55kva": "Data\\cabinet inverter 55kva.pdf",
        "inverter.cabinet_inverter.90kva": "Data\\cabinet inverter 90kva.pdf",
        "inverter.cabinet_inverter.200kva": "Data\\cabinet inverter 200kva.pdf",
        "DC_DC.4kw-900": "Data\\Dc-Dc 4kw.pdf",
        "DC_DC.6kw-750": "Data\\Dc-Dc 6kw.pdf",
        "OBC.450V": "Data\\OBC 450v.pdf",
        "OBC.800V": "Data\\OBC 800v.pdf",
        "OBC.850V": "Data\\OBC 850v.pdf",
        "BCS.IP68housing": "Data\\BCS ip68.pdf",
        "BCS.Cabinet/Component":"Data\\BCS cabinet_component.pdf"
    }
    
    if button_path and button_path in source_mapping:
        filter_dict = {"source": source_mapping[button_path]}
        return docsearch.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": 3,
                "filter": filter_dict
            }
        )
    return docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})

# Initialize Gemini LLM
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-8b", google_api_key=GEMINI_API_KEY)

# Create prompt templates
product_prompt = ChatPromptTemplate.from_messages([
    ("human", "Context: {context}\n\nProvide detailed information about {input} including its specifications and applications in structure way in less words don't provide missing information")
])

general_prompt = ChatPromptTemplate.from_messages([
    ("human", "Context: {context}\n\nQuestion: {input}\n\nProvide a helpful and accurate response based on the context provided, don't provide missing information if question is not related to provide context then don't give answer and user say good morning or any type of greeting text answer that question.")
])

# Create chains
def create_qa_chains(retriever):
    product_qa_chain = create_stuff_documents_chain(llm, product_prompt)
    general_qa_chain = create_stuff_documents_chain(llm, general_prompt)
    
    return (
        create_retrieval_chain(retriever, product_qa_chain),
        create_retrieval_chain(retriever, general_qa_chain)
    )

# Updated Button hierarchy configuration
BUTTON_HIERARCHY = {
    "inverter": {
        "label": "Inverter",
        "children": {
            "aux_inverter": {
                "label": "Auxiliary Inverter",
                "children": {
                    "single_inverter": {
                        "label": "Single Inverter",
                        "children": {
                            "17kva": {"label":"17 kVA", "children": {}},
                            "28kva": {"label": "28 kVA", "children": {}}
                        }
                    },
                    "Dual_inverter": {
                        "label": "Dual Inverter",
                        "children": {
                            "2x15kva": {"label": "2x15 kVA", "children": {}},
                            "2x17kva": {"label": "2x17 kVA", "children": {}},
                            "2x28kva": {"label": "2x28 kVA", "children": {}}, 
                            "2x30kva": {"label": "2x30 kVA", "children": {}},
                            "2x55kva": {"label": "2x55 kVA", "children": {}}
                        }
                    }
                }
            },
            "traction_inverter": {
                "label": "Traction Inverter",
                "children": {
                    "80kva": {"label": "80 kVA", "children": {}},
                    "160kva": {"label": "160 kVA", "children": {}},
                    "150kva": {"label": "150 kVA", "children": {}},
                    "320kva": {"label": "320 kVA", "children": {}},
                    "320kva-HPP": {"label": "320 kVA-HPP", "children": {}}
                }
            },
            "combi_inverter": {
                "label": "Combi Inverter",
                "children": {
                    "17k3k": {"label": "17k3k", "children": {}},
                }
            },
            "cabinet_inverter":{
                "label":"Cabinet Inverter",
                "children":{
                    "8kva": {"label": "8 kVA", "children": {}},
                    "22kva": {"label": "22 kVA", "children": {}},
                    "55kva": {"label": "55 kVA", "children": {}}, 
                    "90kva": {"label": "90 kVA", "children": {}},
                    "200kva": {"label": "200 kVA", "children": {}}
                }
            }
        }
    },
    "DC_DC": {
        "label": "DC-DC",
        "children": {
            "4kw-900": {"label":"4kW-900", "children":{}},
            "6kw-750": {"label":"6kW-750", "children":{}}
        }
    },
    "OBC": {
        "label": "On-Board Charger",
        "children": {
            "450V": {"label":"450V", "children":{}},
            "800V": {"label":"800V", "children":{}},
            "850V": {"label":"850V", "children":{}}
        }
    },
    "BCS": {
        "label": "Battery charging station",
        "children": {
            "IP68housing": {"label":"IP 68 housing", "children":{}},
            "Cabinet/Component":{"label":"Cabinet/Component","children":{}}
        }
    },
    "Customize":{
        "label":"Customize Product",
        "children":{}
    }
}

def get_root_buttons():
    return [
        {"label": value["label"], "value": key}
        for key, value in BUTTON_HIERARCHY.items()
    ]

def get_button_label(button_path):
    if not button_path:
        return ""
        
    parts = button_path.split('.')
    current = BUTTON_HIERARCHY
    labels = []
    
    for part in parts:
        if part in current:
            labels.append(current[part]["label"])
            current = current[part].get("children", {})
    
    return " - ".join(labels)

def get_pdf_url_for_path(button_path):
    if not button_path:
        return None
    
    parts = button_path.split('.')
    current = BUTTON_HIERARCHY
    
    for part in parts:
        if part in current:
            if "pdf_url" in current[part]:
                return current[part]["pdf_url"]
            current = current[part]["children"]
    
    return None

def get_current_level_and_label(button_path):
    if not button_path:
        return BUTTON_HIERARCHY, ""
    
    parts = button_path.split('.')
    current = BUTTON_HIERARCHY
    current_label = ""
    
    for part in parts:
        if part in current:
            current_label = current[part]["label"]
            current = current[part]["children"]
    
    return current, current_label


@app.route('/submit_customize_data', methods=['POST'])
def submit_customize_data():
    try:
        data = request.json  # Get JSON data from the request

        # Create a new UserData instance
        new_user_data = UserData(
            phone=data['phone'],
            email=data['email'],
            description=data['description']
        )

        # Add to the database
        db.session.add(new_user_data)
        db.session.commit()

        return jsonify({'message': 'Data stored successfully'}), 200
    except Exception as e:
        logger.error(f"Error storing user data: {str(e)}")
        return jsonify({'error': 'Failed to store data'}), 500


@app.route("/")
def index():
    return render_template('chat.html')

@app.route("/get_greeting", methods=["GET"])
def get_greeting():
    return jsonify({
        "greeting": "👋 Hello! How can REFU Ai assist you today? Please select a category to explore:",
        "buttons": get_root_buttons()
    })

def get_pdf_url_for_product(button_path):
    if not button_path:
        return None
    
    # Mapping logic here (if needed)
    return None




@app.route("/get_buttons", methods=["POST"])
def get_buttons():
    selected_button = request.form.get("selected_button")
    
    current_level, current_label = get_current_level_and_label(selected_button)
    
    buttons = []
    has_children = False
    
    if current_level:
        for key, value in current_level.items():
            button_value = f"{selected_button}.{key}" if selected_button else key
            buttons.append({
                "label": value["label"],
                "value": button_value
            })
            if value.get("children") and len(value["children"]) > 0:
                has_children = True
    
    pdf_url = get_pdf_url_for_product(selected_button)
    
    response = {
        "buttons": buttons,
        "current_label": current_label,
        "has_children": has_children,
        "pdf_url": pdf_url
    }
    return jsonify(response)

@app.route("/get", methods=["POST"])
def chat():
    msg = request.form.get("msg")
    button_path = request.form.get("button_path")
    
    if not msg:
        return jsonify({"error": "No message provided"}), 400

    try:
        filtered_retriever = create_filtered_retriever(button_path)
        product_rag_chain, general_rag_chain = create_qa_chains(filtered_retriever)

        # Check if this is a "yes" response to seeing a cooling graph
        if msg.lower() in ["yes", "yes please", "show graph"] and button_path:
            # Return cooling graph data for the specific model
            return jsonify({
                "type": "cooling_graph",
                "modelName": button_path,
                "coolingImageUrl": f"/static/cooling_graphs/{button_path.replace('.', '_')}.png"
            })

        if msg.startswith("Tell me about "):
            button_path = msg.replace("Tell me about ", "")
            button_label = get_button_label(button_path)
            
            if not button_label:
                return "I couldn't find information about that specific product. Please try another query.", 404
            
            response = product_rag_chain.invoke({"input": button_label})
        else:
            response = general_rag_chain.invoke({"input": msg})
            
            # If query contains cooling-related terms for a specific model
            if any(term in msg.lower() for term in ["cooling", "temperature", "thermal"]) and button_path:
                response["answer"] = response["answer"] + "\n\nWould you like to see the cooling performance graph for this model?"
        
        if not response or not response.get("answer"):
            return "I apologize, but I couldn't find a relevant answer. Could you please rephrase your question?", 404
        
        answer = response["answer"]  
        paragraphs = answer.split("\n\n")
        formatted_response = "".join(f"<p>{para}</p>" for para in paragraphs)

        return formatted_response
        
    except Exception as e: 
        logger.error(f"Error processing request: {str(e)}")
        return "I apologize, but I encountered an error processing your request. Please try again.", 500
    

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)
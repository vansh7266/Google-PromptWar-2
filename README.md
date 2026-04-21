# Google-PromptWar-2

## ElectoGuide: Advanced Election Assistant

ElectoGuide is a highly polished, secure, and accessible assistant built to educate citizens on the election process. It uses Google Cloud Vertex AI to deliver real-time, streaming educational content.

### Project Structure

- **[electoguide-project/](file:///Users/vanshgupta/Desktop/Google-PromptWar-2/electoguide-project/)**: The main application directory containing the backend logic, frontend assets, and deployment configuration.

### Key Features

- **Vertex AI Integration**: Real-time educational content delivery.
- **Security First**: DOMPurify for XSS prevention and IAM Service Accounts for secure access.
- **High Performance**: Streaming responses for zero-latency user experience.
- **Accessibility**: A11y-compliant UI with semantic HTML and aria-labels.

### Quick Start

To run the project locally:

1. Navigate to the project directory:
   ```bash
   cd electoguide-project
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```
4. Open [http://localhost:8080](http://localhost:8080) in your browser.

For more details, see the [project README](file:///Users/vanshgupta/Desktop/Google-PromptWar-2/electoguide-project/README.md).

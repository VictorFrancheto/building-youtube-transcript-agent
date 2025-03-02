from youtube_transcript_api import YouTubeTranscriptApi
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
from langchain.tools import Tool
from langchain.agents import initialize_agent, AgentType

class YouTubeTranscriptionAgent:
    """
    This class encapsulates the complete workflow to:
      1. Extract the video ID and transcript from a YouTube video.
      2. Split the transcript into smaller chunks for better processing.
      3. Generate a summary, extract main topics, and important quotes using a language model.
      4. Process user queries and select the appropriate tool.
    """
    
    def __init__(self, model: str = "llama3"):
        """
        Initializes the agent with the name of the language model to be used.
        
        Args:
            model (str): The name of the LLM (default: "llama3").
        """
        self.model = model

    def extract_video_id(self, url: str) -> str:
        """
        Extracts the video ID from the YouTube URL.
        
        Examples of URLs:
          - https://www.youtube.com/watch?v=VIDEO_ID
          - https://youtu.be/VIDEO_ID
        
        Args:
            url (str): The full video URL.
        
        Returns:
            str: The extracted video ID.
        """
        if "youtu.be" in url:
            return url.split("/")[-1]
        if "=" in url:
            return url.split("=")[-1]
        return url

    def get_transcript(self, url: str) -> str:
        """
        Retrieves the transcript of the YouTube video and returns a continuous text.
        
        Steps:
          1. Extract the video ID using 'extract_video_id'.
          2. Request the transcript via the API.
          3. Concatenate the text segments and perform basic cleaning.
        
        Args:
            url (str): The YouTube video URL.
        
        Returns:
            str: The transcript text or an error message if retrieval fails.
        """
        video_id = self.extract_video_id(url)
        try:
            # Request the transcript (a list of dictionaries with the key "text")
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            # Join the text segments into a single string
            text = " ".join([item["text"] for item in transcript])
            # Clean up: remove line breaks and single quotes
            text = text.replace("\n", " ").replace("'", "")
            return text
        except Exception as e:
            return f"Failed to get the transcript: {str(e)}"

    def create_chunks(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> list:
        """
        Splits the text into smaller chunks for easier processing.
        
        Args:
            text (str): The complete text to be split.
            chunk_size (int): Approximate number of characters per chunk (default: 1000).
            overlap (int): Number of overlapping characters between chunks (default: 100).
        
        Returns:
            list: A list of text chunks.
        """
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
        return splitter.split_text(text)

    def generate_summary(self, chunks: list) -> str:
        """
        Generates a unified summary from multiple text chunks.
        
        Steps:
          1. For each chunk, generate a mini-summary using the model.
          2. Combine all mini-summaries into a single string.
          3. Process the combined string to create a final coherent summary in English.
        
        Args:
            chunks (list): A list of text chunks.
        
        Returns:
            str: A coherent summary of the video's content in English.
        """
        llm = OllamaLLM(model=self.model)
        
        # Template to generate a mini-summary for each chunk
        template = """Text: {text}
Objective: Summarize the provided text.
Answer:"""
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | llm

        # Generate a mini-summary for each chunk
        summaries = [chain.invoke({"text": chunk}) for chunk in chunks]
        combined_summary = " ".join(summaries)

        # Template to synthesize the mini-summaries into a final summary
        final_template = """Multiple summaries: {summaries}
Objective: Create a single, coherent summary in English.
Answer:"""
        final_prompt = ChatPromptTemplate.from_template(final_template)
        final_chain = final_prompt | llm
        final_summary = final_chain.invoke({"summaries": combined_summary})
        return final_summary

    def extract_topics(self, chunks: list) -> list:
        """
        Extracts the main topics from the text chunks.
        
        Args:
            chunks (list): A list of text chunks.
        
        Returns:
            list: A unique list of main topics.
        """
        llm = OllamaLLM(model=self.model)
        template = """Text: {text}
Objective: Extract the main topics from the provided text.
Answer: List the topics separated by commas."""
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | llm

        topic_lists = [chain.invoke({"text": chunk}) for chunk in chunks]
        all_topics = set()
        for topics in topic_lists:
            # Split the response by commas and remove extra spaces
            items = [t.strip() for t in topics.split(",")]
            all_topics.update(items)
        # Remove empty items
        all_topics = {t for t in all_topics if t}
        return list(all_topics)

    def extract_quotes(self, chunks: list) -> list:
        """
        Extracts important quotes from the text chunks.
        
        Args:
            chunks (list): A list of text chunks.
        
        Returns:
            list: A list containing unique quotes.
        """
        llm = OllamaLLM(model=self.model)
        template = """Text: {text}
Objective: Extract the most important quote from the text.
Answer: Provide the quote as plain text."""
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | llm

        quotes = [chain.invoke({"text": chunk}) for chunk in chunks]
        unique_quotes = []
        seen = set()
        for quote in quotes:
            normalized = quote.strip().lower()
            if normalized and normalized not in seen:
                unique_quotes.append(quote.strip())
                seen.add(normalized)
        return unique_quotes

    def process_user_query(self, query: str, chunks: list) -> str:
        """
        Processes the user's query by selecting the appropriate tool (summary, topics, or quotes)
        and generates a response.
        
        Steps:
          1. Define wrapper functions for each tool to simplify invocation without parameters.
          2. Create a list of Tools with name, function, and description.
          3. Initialize a LangChain agent with the defined tools.
          4. Invoke the agent with the user's query.
          5. If a parsing error occurs, catch the exception and return an error message.
        
        Args:
            query (str): The user's question or instruction.
            chunks (list): A list of text chunks from the transcript.
        
        Returns:
            str: The response generated by the agent or an error message in case of failure.
        """
        llm = OllamaLLM(model=self.model)
        
        # Wrapper functions for each tool
        def summary_wrapper(_=""):
            return self.generate_summary(chunks)
        
        def topics_wrapper(_=""):
            return self.extract_topics(chunks)
        
        def quotes_wrapper(_=""):
            return self.extract_quotes(chunks)
        
        tools = [
            Tool(
                name="generate_summary",
                func=summary_wrapper,
                description="Generates a detailed summary of the transcript."
            ),
            Tool(
                name="extract_topics",
                func=topics_wrapper,
                description="Extracts the main topics of the transcript."
            ),
            Tool(
                name="extract_quotes",
                func=quotes_wrapper,
                description="Extracts important quotes from the transcript."
            )
        ]
        
        # Initialize the agent with the tools and configure it to use ZERO_SHOT_REACT_DESCRIPTION
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True  # Enables detailed debug messages
        )
        
        # Try to invoke the agent with the query; if a parsing error occurs, catch the exception
        try:
            response = agent.invoke(input=query, handle_parsing_errors=True)
            return response
        except Exception as e:
            return f"Agent error: {e}"

# Main execution block
if __name__ == "__main__":
    # Create an instance of the agent with the desired model
    agent = YouTubeTranscriptionAgent(model="llama3")
    
    # Example YouTube video URL
    example_url = "https://www.youtube.com/watch?v=1aA1WGON49E"
    
    # Retrieve the transcript of the video
    transcript_text = agent.get_transcript(example_url)
    
    # If an error occurs while getting the transcript, display the error message
    if transcript_text.startswith("Failed to get"):
        print(transcript_text)
    else:
        # Split the transcript text into chunks for processing
        text_chunks = agent.create_chunks(transcript_text)
        
        # Example user query to get a summary
        user_query = "Can you provide a summary of this video?"
        
        # Process the query and get the agent's response
        result = agent.process_user_query(user_query, text_chunks)
        print("Response:", result)

from bson.regex import Regex
from fastapi import FastAPI,Depends,HTTPException
from pydantic import BaseModel
import uvicorn
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

#Using Pydantic model
class Book(BaseModel):
    title: str
    author: str
    description: str
    price: float
    stock: int
app = FastAPI()

#creating connection to MongoDB
client = AsyncIOMotorClient("mongodb://localhost:27017")
database= client["bookstore"]
collection = database["books"]

# Create an index for the field "title".
collection.create_index("title")

# Create a compound index for the fields "title" and "author".
collection.create_index([("title", 1), ("author", 1), ("price",1),('stock',1)])




# GET API - fetching data from database
@app.get("/books")
async def get_books():
    books = []
    async  for book in collection.find({}, {"_id": 0}):  # Exclude the _id field
        books.append(book)
    return books

# searching for book filtered by title, author and price range
@app.get("/search")
async def search(title: str = None, author: str = None,
                 min_price: float = None, max_price: float = None):
    books = await search_books(title, author, min_price, max_price)
    return {"books": books}

# POST API - Adding a new book with HTTP validation 
@app.post("/books")
async def create_book(book: Book):
    try:
        book_data = book.dict()
        if book_data["stock"] < 0:
            raise HTTPException(status_code=400, detail="Stock must be a non-negative value")
        if book_data["price"] < 0:
            raise HTTPException(status_code=400, detail="Price must be a non-negative value")
        if any(value is None or value.strip() == "" for value in book_data.values() if isinstance(value, str)):
            raise HTTPException(status_code=400, detail="Empty string values are not allowed")
        await collection.insert_one(book_data)
        return {"message": "Book created successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# UPDATE API - Updating an existing book by id 
@app.put("/books/{book_id}")
async def update_book(book_id: str, book: Book):
    updated_book = book.dict()
    result = await collection.update_one({"_id": ObjectId(book_id)}, {"$set": updated_book})
    #book["_id"] = str(book["_id"])
    if result.modified_count == 1:
        return {"message": "Book updated successfully"}
    else:
        return {"message": "Book not found"}
    
# DELETE API - Deleting a book by id 
@app.delete("/books/{book_id}")
async def delete_book(book_id: str):
    result = await collection.delete_one({"_id": ObjectId(book_id)})
    if result.deleted_count == 1:
        return {"message": "Book deleted successfully"}
    else:
        return {"message": "Book not found"}


#Using Aggregation queries
###################################

#fetching top selling books
@app.get("/stats/best-selling")
async def get_best_selling_books():
    pipeline = [
        {"$group": {"_id": "$title", "totalSold": {"$sum": "$stock"}}},
        {"$sort": {"totalSold": -1}},
        {"$limit": 5}
    ]
    result = await collection.aggregate(pipeline).to_list(length=None)
    return result

#searching total number of books
@app.get("/stats/total-books")
async def get_total_books():
    pipeline = [{"$count": "total_books"}]
    result = await collection.aggregate(pipeline).to_list(length=None)
    if result:
        return result[0]["total_books"]
    else:
        return 0


#fetching top selling author
@app.get("/stats/top-authors")
async def get_top_authors():
    pipeline = [
        {"$group": {"_id": "$author", "totalBooks": {"$sum": 1}}},
        {"$sort": {"totalBooks": -1}},
        {"$limit": 5}
    ]
    result = await collection.aggregate(pipeline).to_list(length=None)
    return result


#fetching a book by id
@app.get("/books/{book_id}")
async def get_book_by_id(book_id: str):

    try:
        book = await collection.find_one({"_id": ObjectId(book_id)})
        if book:
            book["_id"] = str(book["_id"])
            return book
        else:
            raise HTTPException(status_code=404, detail="Book not found")
    except:
        raise HTTPException(status_code=400, detail="Invalid book ID")
    

#fetching books by titles
async def get_books_by_title(title: str):
    # Perform a case-insensitive search for books by author name
    query = {"title": {"$regex": f".*{title}.*", "$options": "i"}}
    books_cursor = collection.find(query)

    # Convert the MongoDB documents to Book objects
    book_objects = []
    async for book in books_cursor:
        book_objects.append(Book(**book))

    return book_objects

#searching book by title
@app.get("/books/by_title/{title}")
async def search_books_by_title(title: str):
    books = await get_books_by_title(title)
    if books:
        return {"books": books}
    else:
        raise HTTPException(status_code=404, detail="Book not found")

# filtering books by author
async def get_books_by_author(author: str):
    # Perform a case-insensitive search for books by author name
    query = {"author": {"$regex": f".*{author}.*", "$options": "i"}}
    books_cursor = collection.find(query)

    # Convert the MongoDB documents to Book objects
    book_objects = []
    async for book in books_cursor:
        book_objects.append(Book(**book))

    return book_objects

# searching books by author
@app.get("/books/by_author/{author}")
async def search_books_by_author(author: str):
    books = await get_books_by_author(author)
    if books:
        return {"books": books}
    else:
        raise HTTPException(status_code=404, detail="Book not found")

# filtering books by price range
async def get_books_by_price_range(min_price: float, max_price: float):
    # Perform a search for books within the specified price range
    query = {"price": {"$gte": min_price, "$lte": max_price}}
    books_cursor = collection.find(query)

    # Convert the MongoDB documents to Book objects
    book_objects = []
    async for book in books_cursor:
        book_objects.append(Book(**book))

    return book_objects

# searching books by price range
@app.get("/books/by_price_range/")
async def search_books_by_price_range(min_price: float, max_price: float):
    books = await get_books_by_price_range(min_price, max_price)
    return {"books": books}


#searching by path parameter
async def search_books(title: str = None, author: str = None,
                        min_price: float = None, max_price: float = None):
    query = {}

    if title:
        query["title"] = {"$regex": title, "$options": "i"}

    if author:
        query["author"] = {"$regex": author, "$options": "i"}

    if min_price is not None or max_price is not None:
        query["price"] = {}

        if min_price is not None:
            query["price"]["$gte"] = min_price

        if max_price is not None:
            query["price"]["$lte"] = max_price

    books_cursor = collection.find(query)
    book_objects = []
    async for book in books_cursor:
        book_objects.append(Book(**book))

    return book_objects


if __name__ == "_main_":
    uvicorn.run(app, host="localhost", port=8000)
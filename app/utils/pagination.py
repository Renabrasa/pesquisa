class Paginator:
    def __init__(self, total_items, page=1, per_page=20):
        self.total_items = total_items
        self.page = max(1, page)  # Garantir que página seja >= 1
        self.per_page = max(1, per_page)  # Garantir que per_page seja >= 1
        
    @property
    def total_pages(self):
        return (self.total_items + self.per_page - 1) // self.per_page
    
    @property
    def offset(self):
        return (self.page - 1) * self.per_page
    
    @property
    def has_prev(self):
        return self.page > 1
    
    @property
    def has_next(self):
        return self.page < self.total_pages
    
    def get_pagination_info(self):
        return {
            'page': self.page,
            'per_page': self.per_page,
            'total_items': self.total_items,
            'total_pages': self.total_pages,
            'has_prev': self.has_prev,
            'has_next': self.has_next,
            'prev_page': self.page - 1 if self.has_prev else None,
            'next_page': self.page + 1 if self.has_next else None,
            'offset': self.offset,
            'start_item': self.offset + 1,
            'end_item': min(self.offset + self.per_page, self.total_items)
        }
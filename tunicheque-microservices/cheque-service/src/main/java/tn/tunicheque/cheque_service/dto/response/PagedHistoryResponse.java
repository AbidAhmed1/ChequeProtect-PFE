package tn.tunicheque.cheque_service.dto.response;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class PagedHistoryResponse<T> {
    private List<T> content;
    private long    totalElements;
    private int     totalPages;
    private int     currentPage;
    private int     pageSize;
    private boolean hasNext;
    private boolean hasPrevious;
}